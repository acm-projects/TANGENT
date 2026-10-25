import re

from langgraph.checkpoint.memory import InMemorySaver

from debate.fakes import ScriptedBrain, make_deps
from debate.graph import build_graph
from debate.runner import build_resume, merge_pending, run_segment
from debate.schemas import AskAction, Claim, FinishAction, OpponentView, Question, TurnOutput
from helpers import drive, make_config, run

SIDE_WORDS = re.compile(r"\b(for|against)\b", re.IGNORECASE)


def turns_of(values, phase=None, side=None, rnd=None):
    return [
        t
        for t in values["turns"]
        if (phase is None or t["phase"] == phase)
        and (side is None or t["side"] == side)
        and (rnd is None or t["round"] == rnd)
    ]


def test_happy_path_events_metrics_and_blindness():
    brain = ScriptedBrain()
    deps = make_deps(brain)
    values, segments, _ = run(drive(deps, rounds=2))

    assert [s.status for s in segments] == ["done"]
    assert values["end_reason"] == "rounds_exhausted"
    assert deps.writer.calls == 1

    phases = [e["phase"] for e in deps.emitter.of("phase_changed")]
    assert phases == ["intake", "research", "opening", "rebuttal", "rebuttal", "closing", "done"]

    assert set(OpponentView.model_fields) == {"argument", "claims"}
    for ctx in brain.contexts:
        if ctx.phase in ("research", "opening"):
            assert ctx.opponent is None
        if ctx.phase == "rebuttal":
            assert ctx.opponent is not None

    rebuttal_events = [e for e in deps.emitter.of("turn_completed") if e["phase"] == "rebuttal"]
    assert len(rebuttal_events) == 4
    assert all(any("opponent claim" in t for t in e["thinking"]) for e in rebuttal_events)
    assert len(deps.emitter.of("thinking")) >= 2

    assert all(isinstance(m["duration_ms"], int) and m["duration_ms"] >= 0 for m in values["metrics"])
    assert {"frame", "agent", "search", "judge"} <= {m["node"] for m in values["metrics"]}
    assert deps.writer.results["d1"]["timings"] == values["metrics"]


def test_judge_view_is_anonymous_and_winner_maps_back():
    seen = set()
    for seed in range(1, 9):
        brain = ScriptedBrain()
        deps = make_deps(brain, seed=seed)
        values, _, _ = run(drive(deps, rounds=1))
        view = brain.judge_views[0]
        assert view.labels == ["A", "B"]
        assert not SIDE_WORDS.search(view.rendered), view.rendered
        assert "Position A" in view.rendered and "Position B" in view.rendered
        assert values["verdict"]["winner_side"] == values["ab_map"]["A"]
        seen.add(values["ab_map"]["A"])
    assert seen == {"for", "against"}


def test_rebuttal_question_from_both_sides_is_deduped_and_resumes():
    q = Question(prompt="What is your budget?")
    q_again = Question(prompt="what is  your budget? ")
    assert q.id == q_again.id and q is not q_again
    script = {
        ("for", "rebuttal", 1, 0): AskAction(questions=[q], thinking="opponent assumes a budget"),
        ("against", "rebuttal", 1, 0): AskAction(questions=[q_again], thinking="need the budget"),
    }
    brain = ScriptedBrain(script)
    deps = make_deps(brain)
    seen = {}

    def on_pause(seg):
        seen["interrupts"] = seg.interrupts
        seen["merged"] = merge_pending(seg.interrupts)
        return build_resume(seg.interrupts, {q.id: "1200"})

    values, segments, _ = run(drive(deps, rounds=2, on_pause=on_pause))
    assert [s.status for s in segments] == ["paused", "done"]
    assert len(seen["interrupts"]) == 2
    assert len(seen["merged"]) == 1 and sorted(seen["merged"][0]["asked_by"]) == ["against", "for"]
    assert [x["answer"] for x in values["user_context"]] == ["1200"]
    assert "-> 1200" in brain.judge_views[0].rendered
    after = [c for c in brain.contexts if c.side == "for" and c.phase == "rebuttal" and c.round == 1 and len(c.steps) == 2]
    assert after and any(x.answer == "1200" for x in after[0].user_context)
    later = [c for c in brain.contexts if c.phase == "closing"]
    assert all(any(x.answer == "1200" for x in c.user_context) for c in later)
    assert values["end_reason"] == "rounds_exhausted"


def test_different_questions_in_parallel_are_both_answered():
    q1, q2 = Question(prompt="Budget?"), Question(prompt="Weight limit?")
    script = {
        ("for", "rebuttal", 1, 0): AskAction(questions=[q1]),
        ("against", "rebuttal", 1, 0): AskAction(questions=[q2]),
    }
    deps = make_deps(ScriptedBrain(script))
    captured = {}

    def on_pause(seg):
        captured["merged"] = merge_pending(seg.interrupts)
        return build_resume(seg.interrupts, {q1.id: "900", q2.id: "1.5kg"})

    values, segments, _ = run(drive(deps, on_pause=on_pause))
    assert len(captured["merged"]) == 2
    assert sorted(x["answer"] for x in values["user_context"]) == ["1.5kg", "900"]
    assert values["result_node_id"]


def test_ask_is_not_allowed_in_closing_even_with_budget_left():
    script = {("for", "closing", 2, 0): AskAction(questions=[Question(prompt="Closing question?")])}
    deps = make_deps(ScriptedBrain(script), ask_cap=5)
    values, segments, _ = run(drive(deps))
    assert [s.status for s in segments] == ["done"]
    assert len(turns_of(values, "closing")) == 2
    assert not values.get("user_context")


def test_ask_cap_is_enforced_per_side():
    q = Question(prompt="Budget?")
    script = {
        ("for", "research", 0, 0): AskAction(questions=[q]),
        ("for", "rebuttal", 1, 0): AskAction(questions=[Question(prompt="Second question?")]),
    }
    deps = make_deps(ScriptedBrain(script), ask_cap=1)
    values, segments, _ = run(drive(deps, on_pause=lambda s: build_resume(s.interrupts, {q.id: "x"})))
    assert [s.status for s in segments] == ["paused", "done"]
    assert [x["prompt"] for x in values["user_context"]] == ["Budget?"]
    assert len(turns_of(values, "rebuttal", "for")) == 2


def test_frame_questions_pause_before_research():
    q = Question(prompt="Which use case?")
    brain = ScriptedBrain(frame_questions=[q])
    deps = make_deps(brain)
    values, segments, _ = run(drive(deps, on_pause=lambda s: build_resume(s.interrupts, {q.id: "coding"})))
    assert [s.status for s in segments] == ["paused", "done"]
    assert values["user_context"][0]["asked_by"] == "frame"


def test_frame_is_redone_with_the_users_answers_so_the_proposition_reflects_them():
    q = Question(prompt="What did you mean by it?")
    seen = []

    class Recording(ScriptedBrain):
        async def frame(self, topic, context):
            seen.append(topic)
            return await super().frame(topic, context)

    brain = Recording(frame_questions=[q])
    values, _, _ = run(drive(make_deps(brain), on_pause=lambda s: build_resume(s.interrupts, {q.id: "Trying to become an NFL player"})))
    assert len(seen) == 2
    assert "Trying to become an NFL player" in seen[1] and "User clarifications" in seen[1]
    assert "User clarifications" not in seen[0]
    assert values["pending_frame_questions"] == []


def test_skipping_the_frame_questions_does_not_cost_a_second_frame_call():
    q = Question(prompt="Which use case?")
    seen = []

    class Recording(ScriptedBrain):
        async def frame(self, topic, context):
            seen.append(topic)
            return await super().frame(topic, context)

    brain = Recording(frame_questions=[q])
    run(drive(make_deps(brain), on_pause=lambda s: build_resume(s.interrupts, {}, skip=True)))
    assert len(seen) == 1


def test_all_rounds_always_run_and_nothing_can_end_them_early():
    brain = ScriptedBrain()
    values, _, _ = run(drive(make_deps(brain), rounds=3))
    assert values["end_reason"] == "rounds_exhausted"
    assert [t["round"] for t in turns_of(values, "rebuttal", "for")] == [1, 2, 3]
    assert len(turns_of(values, "closing")) == 2


def test_user_picks_a_side_mid_debate():
    brain = ScriptedBrain()
    deps = make_deps(brain)

    def trip(ctx):
        if ctx.phase == "rebuttal" and ctx.round == 1 and ctx.side == "for":
            deps.control.request("d1", "pick_side", "against")

    brain.on_step = trip
    values, _, _ = run(drive(deps, rounds=3))
    assert values["end_reason"] == "user_picked"
    assert not turns_of(values, "rebuttal", rnd=2)
    closings = turns_of(values, "closing")
    assert [t["side"] for t in closings] == ["against"]
    label = {v: k for k, v in values["ab_map"].items()}["against"]
    assert brain.fixed_winners == [label]
    assert values["verdict"]["winner_side"] == "against"
    payload = deps.writer.results["d1"]
    assert payload["winner"] == "against" and payload["end_reason"] == "user_picked"
    assert payload["picked_side"] == "against"
    assert deps.writer.calls == 1


def test_user_stop_without_pick_lets_the_judge_decide():
    brain = ScriptedBrain()
    deps = make_deps(brain)

    def trip(ctx):
        if ctx.phase == "rebuttal" and ctx.round == 1 and ctx.side == "for":
            deps.control.request("d1", "stop")

    brain.on_step = trip
    values, _, _ = run(drive(deps, rounds=3))
    assert values["end_reason"] == "user_stopped"
    assert not turns_of(values, "closing")
    assert brain.fixed_winners == [None]
    assert values["result_node_id"]


def test_control_while_waiting_for_an_answer_skips_the_question():
    q = Question(prompt="Budget?")
    script = {
        ("for", "rebuttal", 1, 0): AskAction(questions=[q]),
        ("against", "rebuttal", 1, 0): AskAction(questions=[q]),
    }
    deps = make_deps(ScriptedBrain(script))

    def on_pause(seg):
        deps.control.request("d1", "pick_side", "for")
        return build_resume(seg.interrupts, skip=True)

    values, segments, _ = run(drive(deps, rounds=3, on_pause=on_pause))
    assert [s.status for s in segments] == ["paused", "done"]
    assert values["end_reason"] == "user_picked"
    assert not values.get("user_context")
    assert all(t["truncated"] for t in turns_of(values, "rebuttal", rnd=1))
    assert [t["side"] for t in turns_of(values, "closing")] == ["for"]
    assert not turns_of(values, "rebuttal", rnd=2)


def test_budget_exhaustion_goes_straight_to_the_judge():
    deps = make_deps(ScriptedBrain(), max_agent_steps=5)
    values, _, _ = run(drive(deps, rounds=3))
    assert values["end_reason"] == "budget_exhausted"
    assert not turns_of(values, "rebuttal") and not turns_of(values, "closing")
    assert values["result_node_id"]


def test_unverified_citations_are_flagged_for_the_judge_and_dropped_from_the_node():
    bad = FinishAction(
        turn=TurnOutput(
            argument="argument with a bad source",
            claims=[Claim(id="x-1", text="claim with fake source", evidence_ids=["ev-fake-9"])],
        )
    )
    script = {("for", "rebuttal", 1, 0): bad}
    brain = ScriptedBrain(script)
    deps = make_deps(brain)
    values, _, _ = run(drive(deps, rounds=1))
    assert values["citation_report"]["for"] == ["ev-fake-9"]
    assert "Unverified citation ids in Position" in brain.judge_views[0].rendered
    assert "ev-fake-9" not in [c["id"] for c in deps.writer.results["d1"]["citations"]]


def test_resume_works_on_a_fresh_graph_instance_like_a_new_lambda_invocation():
    q = Question(prompt="Budget?")
    script = {("for", "rebuttal", 1, 0): AskAction(questions=[q])}
    deps = make_deps(ScriptedBrain(script))
    saver = InMemorySaver()
    cfg = make_config(deps)

    async def go():
        g1 = build_graph(saver)
        seg = await run_segment(g1, cfg, {"debate_id": "d1", "topic": "t", "rounds": 2})
        assert seg.status == "paused" and len(seg.interrupts) == 1
        g2 = build_graph(saver)
        seg2 = await run_segment(g2, cfg, build_resume(seg.interrupts, {q.id: "1200"}))
        return seg2, await g2.aget_state(cfg)

    seg2, snap = run(go())
    assert seg2.status == "done"
    assert snap.values["result_node_id"] == "node-d1"


def test_time_slicing_matches_an_uninterrupted_run():
    base_values, _, _ = run(drive(make_deps(), rounds=2))

    ticks = {"n": 0}

    def time_left():
        ticks["n"] += 1
        return 0 if ticks["n"] % 3 == 0 else 10**9

    deps = make_deps()
    values, segments, _ = run(drive(deps, rounds=2, time_left_ms=time_left, min_slice_ms=1, max_segments=80))
    assert len(segments) > 3
    assert segments[-1].status == "done"
    key = lambda v: sorted((t["phase"], t["round"], t["side"]) for t in v["turns"])
    assert key(values) == key(base_values)
    assert values["end_reason"] == base_values["end_reason"]
    assert deps.writer.calls == 1
    assert len(values["turns"]) == len(base_values["turns"])


def test_emitter_dedupes_replayed_events():
    deps = make_deps()
    assert run(deps.emitter.emit("thinking", {"text": "a"}, key="k1")) is True
    assert run(deps.emitter.emit("thinking", {"text": "a"}, key="k1")) is False
    assert len(deps.emitter.events) == 1


def test_a_failing_search_does_not_kill_the_debate():
    class Boom:
        async def search(self, query):
            raise RuntimeError("rate limited")

    deps = make_deps(ScriptedBrain())
    deps.search = Boom()
    values, _, _ = run(drive(deps, rounds=1))
    assert values["end_reason"] == "rounds_exhausted"
    assert not values["evidence_pool"]


def test_smoke_script_runs_offline_and_passes_its_own_checks():
    import subprocess, sys, pathlib

    root = pathlib.Path(__file__).resolve().parents[1]
    r = subprocess.run([sys.executable, str(root / "scripts/smoke_debate.py"), "--offline", "--topic", "t", "--rounds", "2",
                        "--auto-answer", "--check"], capture_output=True, text=True, timeout=120, cwd=root)
    assert r.returncode == 0, r.stdout[-1500:] + r.stderr[-1500:]
    assert "FAIL" not in r.stdout and "(auto)" in r.stdout


def test_several_queries_in_one_search_step_run_together_and_count_against_the_cap():
    from debate.schemas import SearchAction
    brain = ScriptedBrain(script={
        ("for", "research", 0, 0): SearchAction(query="alpha one", more_queries=["beta two", "gamma three", "delta four"], thinking="t"),
    })
    deps = make_deps(brain)
    values, segments, _ = run(drive(deps, rounds=1))
    assert [s.status for s in segments] == ["done"]
    assert {"alpha one", "beta two"} <= set(deps.search.queries)
    assert "gamma three" not in deps.search.queries and "delta four" not in deps.search.queries  # at most 2 per call
    tools = [e for e in deps.emitter.of("tool_called") if e["side"] == "for"]
    assert [e["query"] for e in tools][:2] == ["alpha one", "beta two"]
    # the agent is told the result of each query
    ctx = next(c for c in brain.contexts if c.side == "for" and c.phase == "research" and len(c.steps) > 1)
    assert sum(1 for s in ctx.steps if s["type"] == "search") == 2
    assert ctx.searches_left == 2  # cap 4, two used: room left to follow up


def test_cached_search_answers_a_repeat_from_memory_and_shares_concurrent_calls():
    import asyncio
    from debate.fakes import FakeSearch
    from debate.search_s2 import CachedSearch

    async def go():
        inner = FakeSearch()
        c = CachedSearch(inner)
        a, b = await asyncio.gather(c.search("Remote  Work"), c.search("remote work"))
        again = await c.search("remote work")
        return inner.queries, a, b, again, c.hits

    queries, a, b, again, hits = asyncio.run(go())
    assert len(queries) == 1 and a == b == again and hits == 2


def test_cached_search_does_not_cache_failures():
    import asyncio
    from debate.search_s2 import CachedSearch

    class Flaky:
        n = 0
        async def search(self, q):
            self.n += 1
            if self.n == 1:
                raise RuntimeError("down")
            return []

    async def go():
        c = CachedSearch(Flaky())
        try:
            await c.search("x")
        except RuntimeError:
            pass
        return await c.search("x"), c._inner.n

    assert asyncio.run(go()) == ([], 2)