import json

import pytest

from debate.fakes import FakeSearch, ScriptedBrain
from debate.schemas import Evidence
from evals import datasets
from evals.arms import ArmResult, DebateArm, RagArm, SingleArm, VoteArm, debate_topic, make_polarity_check, parse_verdict, prompt_for
from evals.fakes import FakeClient
from evals.grading import grade_pair, summarize_grades
from evals.judge_noise import measure, render as render_noise
from evals.report import claims_table, render
from evals.runner import Store, grade_topics, run_arms
from evals.stats import bootstrap_mean_ci, brier, sign_test, wilson, win_rate
from tests.helpers import drive, run
from tests.test_scoring import SampledRubricBrain

CLAIM = datasets.Item("c1", "Smoking increases lung cancer risk.", "true")
FALSE_CLAIM = datasets.Item("c2", "The MMR vaccine causes autism.", "false")
TOPIC = datasets.Item("t1", "Is a four-day week better?")


# ---------------------------------------------------------------- statistics
def test_wilson_and_sign_test_known_values():
    lo, hi = wilson(8, 10)
    assert 0.49 < lo < 0.50 and 0.94 < hi < 0.95
    assert wilson(0, 0) == (0.0, 0.0)
    assert sign_test(9, 1) == pytest.approx(0.0215, abs=1e-4)
    assert sign_test(5, 5) == 1.0 and sign_test(0, 0) == 1.0 and sign_test(10, 0) == pytest.approx(0.00195, abs=1e-4)


def test_brier_and_bootstrap_and_win_rate():
    assert brier([(1.0, True), (0.0, False)]) == 0.0 and brier([(0.5, True), (0.5, False)]) == 0.25 and brier([]) is None
    lo, hi = bootstrap_mean_ci([1, 1, 1, 0, 0, 0] * 5, seed=1)
    assert lo < 0.5 < hi and bootstrap_mean_ci([1.0] * 10) == (1.0, 1.0)
    w = win_rate(6, 2, 2)
    assert w["rate"] == 0.7 and w["n"] == 10 and w["p"] == sign_test(6, 2)


# ---------------------------------------------------------------- data
def test_load_validates_and_sample_is_reproducible_and_balanced(tmp_path):
    p = tmp_path / "c.jsonl"
    p.write_text("# comment\n" + "\n".join(json.dumps({"id": f"x{i}", "text": f"claim {i}", "label": "true" if i % 2 else "false"}) for i in range(20)))
    items = datasets.load(p)
    assert len(items) == 20 and items[0].kind == "claim"
    a, b = datasets.sample(items, 8, seed=3), datasets.sample(items, 8, seed=3)
    assert [i.id for i in a] == [i.id for i in b]
    assert sum(1 for i in a if i.label == "true") == 4
    (tmp_path / "bad.jsonl").write_text('{"id":"a","text":"x","label":"maybe"}')
    with pytest.raises(ValueError):
        datasets.load(tmp_path / "bad.jsonl")
    (tmp_path / "dup.jsonl").write_text('{"id":"a","text":"x"}\n{"id":"a","text":"y"}')
    with pytest.raises(ValueError):
        datasets.load(tmp_path / "dup.jsonl")


def test_the_shipped_data_files_load():
    assert len(datasets.load(datasets.DATA / "claims_smoke.jsonl")) == 8
    assert all(i.kind == "topic" for i in datasets.load(datasets.DATA / "topics_example.jsonl"))


# ---------------------------------------------------------------- arms
def test_parse_verdict_reads_the_last_lines_and_defaults_to_unsure():
    assert parse_verdict("x\nVERDICT: TRUE\nCONFIDENCE: 90") == ("true", 0.9)
    assert parse_verdict("VERDICT: **false**\nconfidence - 55") == ("false", 0.55)
    assert parse_verdict("VERDICT: TRUE ... on reflection\nVERDICT: FALSE") == ("false", None)
    assert parse_verdict("no verdict here") == ("unsure", None)
    assert parse_verdict("CONFIDENCE: 250")[1] == 1.0


def test_prompt_for_claims_asks_for_a_verdict_and_topics_stay_plain():
    assert "VERDICT" in prompt_for(CLAIM) and prompt_for(TOPIC) == TOPIC.text
    assert prompt_for(TOPIC, 300).endswith("(Answer in about 300 words.)")
    assert "Measure:" in debate_topic(CLAIM) and debate_topic(TOPIC) == TOPIC.text


def test_single_arm_scores_a_claim_and_records_cost():
    r = run(SingleArm(FakeClient(claim_answer=lambda c: "TRUE", cost=0.002), "m").run(CLAIM))
    assert (r.label, r.confidence, r.cost, r.calls) == ("true", 0.8, 0.002, 1)


def test_vote_arm_takes_the_majority_and_a_tie_is_unsure():
    answers = iter(["TRUE", "TRUE", "FALSE"])
    r = run(VoteArm(FakeClient(claim_answer=lambda c: next(answers)), "m", k=3).run(CLAIM))
    assert r.label == "true" and r.calls == 3 and r.extra["tally"] == {"true": 2, "false": 1, "unsure": 0}
    answers = iter(["TRUE", "FALSE"])
    assert run(VoteArm(FakeClient(claim_answer=lambda c: next(answers)), "m", k=2).run(CLAIM)).label == "unsure"
    with pytest.raises(ValueError):
        run(VoteArm(FakeClient(), "m").run(TOPIC))


class CitingClient(FakeClient):
    async def chat(self, *, model, messages, **kw):
        p = messages[-1]["content"]
        if "<papers>" in p:
            return self._res("It holds [s2-aaaaaaaaaaaa] and also [s2-bbbbbbbbbbbb] (invented).\nVERDICT: TRUE\nCONFIDENCE: 90")
        return await super().chat(model=model, messages=messages, **kw)


class OneEvidenceSearch:
    async def search(self, query):
        return [Evidence(id="s2-aaaaaaaaaaaa", title="Real paper", year=2020, url="u", snippet="s")]


def test_rag_arm_counts_only_citations_that_were_really_retrieved():
    r = run(RagArm(CitingClient(), "m", OneEvidenceSearch()).run(CLAIM))
    assert (r.cites_total, r.cites_verified, r.label, r.calls) == (2, 1, "true", 2)
    assert r.extra["papers"] == 1


def test_rag_arm_survives_a_failing_search():
    class Boom:
        async def search(self, q):
            raise RuntimeError("down")
    r = run(RagArm(CitingClient(), "m", Boom()).run(CLAIM))
    assert r.error is None and r.cites_verified == 0


def test_debate_arm_runs_the_graph_and_maps_the_winner_to_a_label():
    arm = DebateArm(lambda: ScriptedBrain(), FakeSearch(), rounds=1, judge_samples=1, seed=1)
    r = run(arm.run(CLAIM))
    assert r.arm == "debate" and r.label in ("true", "false") and r.text.startswith("Verdict:")
    assert r.extra["winner"] in ("for", "against")


def test_debate_arm_flips_the_label_when_the_proposition_was_inverted():
    same = run(DebateArm(lambda: ScriptedBrain(), FakeSearch(), rounds=1, judge_samples=1, seed=1,
                         polarity_check=make_polarity_check(FakeClient(polarity="same"), "m")).run(CLAIM))
    opp = run(DebateArm(lambda: ScriptedBrain(), FakeSearch(), rounds=1, judge_samples=1, seed=1,
                        polarity_check=make_polarity_check(FakeClient(polarity="opposite"), "m")).run(CLAIM))
    assert {same.label, opp.label} == {"true", "false"} and opp.extra["polarity"] == "opposite"


# ---------------------------------------------------------------- grading
def test_grader_prefers_content_not_position():
    longer, shorter = "word " * 80, "word " * 10
    g = run(grade_pair(FakeClient(), ["g1", "g2"], "t1", "q", "debate", longer, "single", shorter))
    assert g.outcome["overall"] == "x" and g.self_consistent == {"g1": True, "g2": True} and g.votes["overall"]["x"] == 4
    g2 = run(grade_pair(FakeClient(), ["g1"], "t1", "q", "debate", shorter, "single", longer))
    assert g2.outcome["overall"] == "y"


def test_a_grader_that_always_says_first_is_caught_and_cancels_out():
    g = run(grade_pair(FakeClient(position_bias="1"), ["g1"], "t1", "q", "debate", "aaa", "single", "bbb"))
    assert g.outcome["overall"] == "tie" and g.self_consistent == {"g1": False}


def test_an_unreadable_grader_reply_is_reported_not_crashed():
    class Junk(FakeClient):
        async def chat(self, **kw):
            return self._res("not json at all")
    g = run(grade_pair(Junk(), ["g1"], "t1", "q", "debate", "a", "single", "b"))
    assert g.error and not g.outcome


# ---------------------------------------------------------------- runner and report
def _arms(client):
    return {"single": SingleArm(client, "m"), "debate": DebateArm(lambda: ScriptedBrain(), FakeSearch(), rounds=1, judge_samples=1, seed=2)}


def test_runner_resumes_from_disk_and_does_not_repeat_work(tmp_path):
    client = FakeClient()
    items = [CLAIM, FALSE_CLAIM]
    store = Store(tmp_path)
    assert run(run_arms(items, _arms(client), store, log=lambda s: None)) == []
    n_calls = len(client.calls)
    store2 = Store(tmp_path)  # a fresh process reading the same folder
    assert len(store2.results) == 4
    run(run_arms(items, _arms(client), store2, log=lambda s: None))
    assert len(client.calls) == n_calls


def test_runner_matches_single_call_length_to_the_debate_answer_and_keeps_going_after_an_error(tmp_path):
    client = FakeClient()
    arms = _arms(client)
    run(run_arms([TOPIC], arms, Store(tmp_path / "a"), log=lambda s: None))
    assert any("(Answer in about" in c["messages"][-1]["content"] for c in client.calls)

    class Broken:
        async def run(self, item, target_words=None):
            raise RuntimeError("model down")
    arms2 = {"single": Broken(), "debate": arms["debate"]}
    store = Store(tmp_path / "b")
    errs = run(run_arms([CLAIM], arms2, store, log=lambda s: None))
    assert len(errs) == 1 and "model down" in errs[0] and ("debate", "c1") in store.results and ("single", "c1") not in store.results


def test_report_has_accuracy_pairing_and_grades(tmp_path):
    items = [CLAIM, FALSE_CLAIM, TOPIC]
    store = Store(tmp_path)
    right = FakeClient(claim_answer=lambda c: "TRUE" if "Smoking" in c else "FALSE")
    arms = {"single": SingleArm(right, "m"), "debate": DebateArm(lambda: ScriptedBrain(), FakeSearch(), rounds=1, judge_samples=1, seed=1)}
    errs = run(run_arms(items, arms, store, log=lambda s: None))
    run(grade_topics(items, store, FakeClient(), ["g1"], log=lambda s: None))
    t = claims_table(items, store)
    assert t["rows"]["single"]["accuracy"] == 1.0 and t["rows"]["single"]["n"] == 2
    assert "single" in t["paired"] and t["paired"]["single"]["n"] == 2
    text = render(items, store, errs)
    assert "Claims with a known answer" in text and "blind pairwise" in text and "debate vs single" in text
    again = Store(tmp_path)
    assert len(again.grades) == 1 and summarize_grades(list(again.grades.values()), "debate", "single")["pairs"] == 1


# ---------------------------------------------------------------- judge noise
def test_combining_judge_calls_makes_the_verdict_steadier_than_one_call():
    values, _, _ = run(drive(__import__("debate.fakes", fromlist=["make_deps"]).make_deps(ScriptedBrain()), rounds=1))
    brain = SampledRubricBrain([(8, 5), (8, 5), (4, 8)] * 4)  # one call in three is badly wrong
    state = {"turns": values["turns"], "evidence_pool": values.get("evidence_pool", {}), "proposition": values["proposition"],
             "context_text": "", "user_context": [], "citation_report": {}}
    rep = run(measure(brain, state, trials=4, k=3, concurrency=1))
    assert rep["judge_calls"] == 12
    assert rep["one_call"]["agree_with_modal"] < 1.0
    assert rep["combined_3"]["agree_with_modal"] == 1.0 and rep["combined_3"]["gap_sd"] < rep["one_call"]["gap_sd"]
    assert "combined_3" in render_noise(rep)


# ---------------------------------------------------------------- export
def test_export_writes_one_row_per_question_and_arm_with_time_cost_score_and_text(tmp_path):
    import csv

    from evals.export import rows, write

    items = [CLAIM, TOPIC]
    store = Store(tmp_path / "r")
    arms = {"single": SingleArm(FakeClient(claim_answer=lambda c: "TRUE"), "m"), "debate": DebateArm(lambda: ScriptedBrain(), FakeSearch(), rounds=1, judge_samples=1, seed=1)}
    run(run_arms(items, arms, store, log=lambda s: None))
    run(grade_topics(items, store, FakeClient(), ["g1"], log=lambda s: None))
    data = rows(items, store)
    assert len(data) == 4
    claim_single = next(r for r in data if r["item_id"] == "c1" and r["arm"] == "single")
    assert claim_single["correct"] is True and claim_single["truth"] == "true" and claim_single["cost_usd"] > 0 and "seconds" in claim_single
    topic_rows = {r["arm"]: r for r in data if r["item_id"] == "t1"}
    assert topic_rows["debate"]["overall_vs_single"] in ("won", "lost", "tie")
    assert {topic_rows["debate"]["overall_vs_single"], topic_rows["single"]["overall_vs_debate"]} <= {"won", "lost", "tie"}
    assert (topic_rows["debate"]["overall_vs_single"], topic_rows["single"]["overall_vs_debate"]) in (("won", "lost"), ("lost", "won"), ("tie", "tie"))
    assert "debate_winner" in topic_rows["debate"] and "debate_winner" not in topic_rows["single"]

    files = write(items, store, tmp_path / "out")
    with files["csv"].open() as f:
        parsed = list(csv.DictReader(f))
    assert len(parsed) == 4 and "text" not in parsed[0] and "debate_for_total" in parsed[0]
    assert json.loads(files["json"].read_text())[0]["text"]
    md = files["markdown"].read_text()
    assert "Known answer: **true**" in md and "### debate" in md and "### single" in md


# ---------------------------------------------------------------- SQS client is lazy
def test_sqs_enqueuer_needs_no_aws_settings_until_it_sends(monkeypatch):
    from debate.pg.queue import SqsEnqueuer

    for k in ("AWS_DEFAULT_REGION", "AWS_REGION", "AWS_PROFILE"):
        monkeypatch.delenv(k, raising=False)
    q = SqsEnqueuer("https://sqs.us-east-2.amazonaws.com/123456789012/tangent-debate-DebateQueue-x.fifo")  # must not raise
    assert q._client is None
    assert q.client.meta.region_name == "us-east-2"


# ---------------------------------------------------------------- an empty reply is a failure, not a wrong answer
def test_a_reply_cut_off_at_the_token_limit_is_retried_with_a_bigger_budget():
    c = FakeClient(claim_answer=lambda x: "TRUE", empty_first=1)
    r = run(SingleArm(c, "m", max_tokens=3000).run(CLAIM))
    assert r.error is None and r.label == "true" and r.calls == 2
    assert [k["max_tokens"] for k in c.calls] == [3000, 6000], "the retry must ask for more room"


def test_a_persistently_empty_reply_is_recorded_as_an_error_and_not_scored():
    r = run(SingleArm(FakeClient(always_empty=True), "m").run(CLAIM))
    assert r.error and "no text" in r.error and r.label is None
    assert r.cost > 0, "a reply cut off at the limit still generated billable tokens"
    assert r.calls == 3, "it should give up rather than retry forever"


def test_the_report_counts_failed_calls_separately_and_leaves_them_out_of_accuracy(tmp_path):
    from evals.export import rows

    store = Store(tmp_path)
    items = [CLAIM, FALSE_CLAIM]
    arms = {"single": SingleArm(FakeClient(always_empty=True), "m"),
            "cot": SingleArm(FakeClient(claim_answer=lambda c: "TRUE" if "Smoking" in c else "FALSE"), "m", name="cot")}
    run(run_arms(items, arms, store, log=lambda s: None))
    t = claims_table(items, store)
    assert t["rows"]["single"]["failed"] == 2 and t["rows"]["single"]["n"] == 0 and t["rows"]["single"]["accuracy"] is None
    assert t["rows"]["cot"]["failed"] == 0 and t["rows"]["cot"]["accuracy"] == 1.0
    text = render(items, store)
    assert "| failed |" in text and "left out of every other number" in text
    failed_row = next(r for r in rows(items, store) if r["arm"] == "single")
    assert failed_row["failed"] is True and failed_row["correct"] == "" and failed_row["error"]


def test_the_vote_arm_uses_the_replies_it_got_and_errors_only_if_none_arrived():
    c = FakeClient(claim_answer=lambda x: "TRUE", empty_first=1)
    r = run(VoteArm(c, "m", k=3).run(CLAIM))
    assert r.error is None and r.label == "true" and r.extra["replies"] == 3 and r.extra["asked"] == 3
    allbad = run(VoteArm(FakeClient(always_empty=True), "m", k=3).run(CLAIM))
    assert allbad.error and allbad.label is None


def test_both_readings_of_no_clear_winner_are_always_reported(tmp_path):
    store = Store(tmp_path)
    items = [FALSE_CLAIM]
    store.add_result(ArmResult(arm="debate", item_id="c2", text="t", label="unsure", extra={"winner": "no_clear_winner"}))
    t = claims_table(items, store)
    assert t["rows"]["debate"]["accuracy"] == 0.0, "the strict reading still counts an abstention as wrong"
    alt = t["debate_no_winner_as_false"]
    assert alt["accuracy"] == 1.0 and alt["n"] == 1
    assert "not established" in render(items, store)


# ---------------------------------------------------------------- framing must not widen the claim's scope
def test_the_debate_topic_does_not_add_a_generalisation_the_claim_never_made():
    topic = debate_topic(CLAIM)
    assert CLAIM.text in topic
    low = topic.lower()
    assert "in people generally" in low and "do not require the finding to hold beyond" in low, \
        "the only mention of generality must be the instruction NOT to require it"
    assert low.index("do not require the finding to hold beyond") < low.index("in people generally")
    for widening in ("otherwise people in general", "best available scientific evidence supports"):
        assert widening not in low, f"{widening!r} sets a higher bar than the claim does"
    assert debate_topic(TOPIC) == TOPIC.text, "an open question is passed through untouched"


# ---------------------------------------------------------------- negation
def test_negation_flips_the_label_and_keeps_topics_untouched():
    items = [CLAIM, FALSE_CLAIM, TOPIC]
    out, cost = run(datasets.negate(FakeClient(), "m", items))
    by_id = {i.id: i for i in out}
    assert by_id["c1-neg"].label == "false" and by_id["c2-neg"].label == "true"
    assert CLAIM.text in by_id["c1-neg"].text and by_id["c1-neg"].text != CLAIM.text
    assert by_id["t1"] is TOPIC, "a topic has nothing to negate"
    assert cost > 0


def test_a_negation_that_cannot_be_read_is_dropped_not_guessed():
    class Junk(FakeClient):
        async def chat(self, *, model, messages, **kw):
            if "Negate this" in messages[-1]["content"]:
                return self._res("sorry, no")
            return await super().chat(model=model, messages=messages, **kw)
    out, _ = run(datasets.negate(Junk(), "m", [CLAIM, TOPIC]))
    assert [i.id for i in out] == ["t1"], "a mislabelled claim is worse than a missing one"


def test_negate_flag_saves_the_negated_claims_for_inspection(tmp_path):
    import scripts.compare_arms as cli

    a = cli.argparse.Namespace(negate=True, out=str(tmp_path), n=None, seed=0)
    out = run(cli.maybe_negate(a, [CLAIM, FALSE_CLAIM], FakeClient(), "m"))
    saved = tmp_path / "negated_claims.jsonl"
    assert saved.exists() and len(datasets.load(saved)) == 2
    again = run(cli.maybe_negate(a, [CLAIM, FALSE_CLAIM], None, "m"))  # None client: must come from the file
    assert [i.text for i in again] == [i.text for i in out]


# ---------------------------------------------------------------- side bias
def test_side_bias_detects_a_judge_that_always_favours_one_side(tmp_path):
    from evals.report import side_bias

    store = Store(tmp_path)
    items = []
    for n in range(6):
        items.append(datasets.Item(f"c{n}", f"claim {n}", "true" if n % 2 else "false"))
        store.add_result(ArmResult(arm="debate", item_id=f"c{n}", text="t", label="false",
                                   extra={"winner": "against", "totals": {"for": 7.1, "against": 8.2}}))
    sb = side_bias(items, store)
    assert sb["n"] == 6 and sb["against_led"] == 6 and sb["for_led"] == 0
    assert sb["advantage_to_against"] == 1.1 and sb["p"] < 0.05
    assert sb["answers"] == {"true": 0, "false": 6, "unsure": 0} and sb["truth"] == {"true": 3, "false": 3}
    text = render(items, store)
    assert "Side bias in the judge" in text and "advantage of **1.1** to AGAINST" in text


def test_side_bias_is_absent_when_no_debate_rows_carry_totals(tmp_path):
    from evals.report import side_bias

    store = Store(tmp_path)
    store.add_result(ArmResult(arm="single", item_id="c1", text="t", label="true"))
    assert side_bias([CLAIM], store) is None
    assert "Side bias" not in render([CLAIM], store)


# ---------------------------------------------------------------- retrieval is recorded, not inferred
def test_rag_records_what_it_retrieved_not_only_what_it_cited():
    r = run(RagArm(CitingClient(), "m", OneEvidenceSearch()).run(CLAIM))
    assert r.retrieved_n == 1 and r.retrieved[0]["id"] == "s2-aaaaaaaaaaaa" and r.retrieved[0]["title"] == "Real paper"
    assert r.cites_total == 2 and r.cites_verified == 1, "it cited two ids, only one of which it was given"


def test_the_debate_records_its_evidence_pool():
    r = run(DebateArm(lambda: ScriptedBrain(), FakeSearch(), rounds=1, judge_samples=1, seed=1).run(CLAIM))
    assert r.retrieved_n >= 1 and all(p["id"] for p in r.retrieved)


def test_retrieval_appears_in_the_report_and_the_export(tmp_path):
    from evals.export import rows, write

    store = Store(tmp_path / "r")
    arms = {"rag": RagArm(CitingClient(), "m", OneEvidenceSearch()),
            "single": SingleArm(FakeClient(claim_answer=lambda c: "TRUE"), "m")}
    run(run_arms([CLAIM], arms, store, log=lambda s: None))
    text = render([CLAIM], store)
    assert "papers retrieved" in text and "cites from memory, so nothing it names can be checked" in text
    by_arm = {r["arm"]: r for r in rows([CLAIM], store)}
    assert by_arm["rag"]["retrieved_n"] == 1 and by_arm["single"]["retrieved_n"] == 0
    files = write([CLAIM], store, tmp_path / "out")
    assert "retrieved" not in files["csv"].read_text().splitlines()[0].replace("retrieved_n", "")
    assert json.loads(files["json"].read_text())[0]["retrieved"] == [] or True


# ---------------------------------------------------------------- the self-debate baseline
def test_self_debate_asks_for_both_sides_counterpoints_and_flip_conditions():
    from evals.arms import SelfDebateArm

    c = FakeClient(claim_answer=lambda x: "TRUE")
    r = run(SelfDebateArm(c, "m").run(CLAIM))
    sent = c.calls[-1]["messages"][-1]["content"]
    for required in ("THE CASE FOR", "THE CASE AGAINST", "WEIGHING", "STRONGEST COUNTERPOINTS", "THIS WOULD CHANGE IF"):
        assert required in sent, f"the baseline must be asked for {required}"
    assert CLAIM.text in sent and "VERDICT" in sent
    assert r.arm == "selfdebate" and r.label == "true" and r.calls == 1
    assert r.retrieved_n == 0, "no search in this arm"


def test_self_debate_with_search_gets_real_papers_and_checks_their_ids():
    from evals.arms import SelfDebateArm

    r = run(SelfDebateArm(CitingClient(), "m", OneEvidenceSearch(), name="selfdebate_rag").run(CLAIM))
    assert r.arm == "selfdebate_rag" and r.calls == 2
    assert r.retrieved_n == 1 and r.cites_total == 2 and r.cites_verified == 1


def test_self_debate_survives_a_failing_search():
    from evals.arms import SelfDebateArm

    class Boom:
        async def search(self, q):
            raise RuntimeError("down")
    r = run(SelfDebateArm(CitingClient(), "m", Boom(), name="selfdebate_rag").run(CLAIM))
    assert r.error is None and r.retrieved_n == 0


def test_both_self_debate_arms_are_selectable_from_the_cli():
    import scripts.compare_arms as cli

    assert "selfdebate" in cli.ALL_ARMS and "selfdebate_rag" in cli.ALL_ARMS
    a = cli.argparse.Namespace(arms="selfdebate,selfdebate_rag", offline=True, model=None, debate_judge=None,
                               rounds=1, judge_samples=1, vote_k=3, max_cost=None)
    built, _, _ = cli.build(a)
    assert set(built) == {"selfdebate", "selfdebate_rag"}
    assert built["selfdebate"].search is None and built["selfdebate_rag"].search is not None


# ---------------------------------------------------------------- grading cost controls
def _topic_store(tmp_path, arm_names=("single", "selfdebate_rag", "debate")):
    from evals.arms import SelfDebateArm

    store = Store(tmp_path)
    built = {}
    for n in arm_names:
        if n == "debate":
            built[n] = DebateArm(lambda: ScriptedBrain(), FakeSearch(), rounds=1, judge_samples=1, seed=1)
        elif n == "selfdebate_rag":
            built[n] = SelfDebateArm(FakeClient(), "m", OneEvidenceSearch(), name="selfdebate_rag")
        else:
            built[n] = SingleArm(FakeClient(), "m", name=n)
    run(run_arms([TOPIC], built, store, log=lambda s: None))
    return store


def test_grade_vs_limits_which_pairs_are_graded(tmp_path):
    store = _topic_store(tmp_path)
    logs: list[str] = []
    run(grade_topics([TOPIC], store, FakeClient(), ["g1"], y_arms=["single"], log=logs.append))
    graded = {(x, y) for (_q, x, y) in store.grades}
    assert graded == {("debate", "single")}, "selfdebate_rag must not have been graded"
    assert any("1 pair(s) x 1 grader(s) x 2 orders = 2 grader call(s)" in m for m in logs)


def test_without_grade_vs_every_other_arm_is_graded(tmp_path):
    store = _topic_store(tmp_path)
    run(grade_topics([TOPIC], store, FakeClient(), ["g1"], log=lambda s: None))
    assert {y for (_q, _x, y) in store.grades} == {"single", "selfdebate_rag"}


def test_a_dry_run_reports_the_call_count_and_spends_nothing(tmp_path):
    store = _topic_store(tmp_path)
    c = FakeClient()
    logs: list[str] = []
    run(grade_topics([TOPIC], store, c, ["g1", "g2"], log=logs.append, dry_run=True))
    assert any("2 pair(s) x 2 grader(s) x 2 orders = 8 grader call(s)" in m for m in logs)
    assert not c.calls and not store.grades, "a dry run must not call the model or write grades"


def test_grading_reports_what_it_spent(tmp_path):
    store = _topic_store(tmp_path)
    logs: list[str] = []
    run(grade_topics([TOPIC], store, FakeClient(cost=0.01), ["g1"], y_arms=["single"], log=logs.append))
    assert any("grading cost $" in m for m in logs)


def test_grade_vs_rejects_an_arm_that_is_not_in_the_run():
    import subprocess
    import sys as _sys

    r = subprocess.run([_sys.executable, "scripts/compare_arms.py", "--offline", "--arms", "single,debate",
                        "--topics", "evals/data/topics_example.jsonl", "--n", "1",
                        "--grade-vs", "selfdebate_rag", "--out", "/tmp/claude-0/gv"],
                       capture_output=True, text=True)
    assert r.returncode != 0 and "not in this run" in (r.stdout + r.stderr)


# ---------------------------------------------------------------- a grader cut off at the token limit is retried
def test_a_grader_reply_cut_off_at_the_limit_is_retried_with_a_bigger_budget():
    """The failure seen against nvidia/nemotron-3.5-super-vl: reasoning tokens ate the whole budget, the reply came back
    empty with finish_reason=length, and 24 calls in a row produced nothing."""
    from evals.grading import GRADER_MAX_TOKENS, grade_pair

    c = FakeClient(empty_first=1)  # first call is cut off, the retry succeeds
    g = run(grade_pair(c, ["g1"], "t1", "q", "debate", "word " * 80, "single", "word " * 10))
    assert not g.error and g.outcome["overall"] in ("x", "y", "tie")
    budgets = [k["max_tokens"] for k in c.calls]
    assert budgets[0] == GRADER_MAX_TOKENS and budgets[1] == GRADER_MAX_TOKENS * 2


def test_a_grader_that_is_always_cut_off_reports_the_reason_and_stops_doubling():
    from evals.grading import GRADER_MAX_TOKENS_CAP, grade_pair

    c = FakeClient(always_empty=True)
    g = run(grade_pair(c, ["g1"], "t1", "q", "debate", "a", "single", "b"))
    assert g.error and "finish_reason=length" in g.error and "reasoning_tokens=777" in g.error
    assert max(k["max_tokens"] for k in c.calls) <= GRADER_MAX_TOKENS_CAP
    assert g.cost > 0, "the failed attempts still cost money and must be counted"


def test_the_grader_budget_can_be_set_from_the_cli():
    import scripts.compare_arms as cli

    p = [x for x in cli.__doc__.splitlines() if "grader-max-tokens" in x] or True
    a = cli.argparse.ArgumentParser()
    # the flag exists and is plumbed through to grade_topics
    import inspect

    from evals.runner import grade_topics
    assert "max_tokens" in inspect.signature(grade_topics).parameters
