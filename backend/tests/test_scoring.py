from debate.fakes import ScriptedBrain, make_deps
from debate.schemas import JudgeVerdict, Usage
from debate.scoring import evidence_score, score_rubric
from tests.helpers import drive, run

CLAIMS = {
    "A1": {"label": "A", "cited": True}, "A2": {"label": "A", "cited": True}, "A3": {"label": "A", "cited": False},
    "B1": {"label": "B", "cited": True}, "B2": {"label": "B", "cited": True},
}
STATS = {"A": {"total": 3, "unverified": 0}, "B": {"total": 2, "unverified": 0}}


def rubric(checks, a=(8, 8, 8), b=(5, 5, 5), leaning="A"):
    return {
        "claim_checks": [{"claim": c, "label": l, "reason": "r"} for c, l in checks.items()],
        "criteria": [
            {"position": "A", "scope": a[0], "engagement": a[1], "fidelity": a[2], "note": "n"},
            {"position": "B", "scope": b[0], "engagement": b[1], "fidelity": b[2], "note": "n"},
        ],
        "leaning": leaning,
    }


ALL_OK = {"A1": "supported", "A2": "supported", "A3": "uncited", "B1": "partly_supported", "B2": "unsupported"}


def test_evidence_score_credits_supported_halves_partly_and_ignores_uncited():
    assert evidence_score({"supported": 2}) == 10.0
    assert evidence_score({"supported": 1, "partly_supported": 2, "unsupported": 1}) == 5.0
    assert evidence_score({"uncited": 4}) == 0.0
    assert evidence_score({"supported": 1, "uncited": 9}) == 10.0


def test_clear_winner_and_exact_totals():
    r = score_rubric(rubric(ALL_OK), CLAIMS, STATS)
    # A: evidence 10, B: evidence 2.5 (partly 0.5 + unsupported 0 of 2 checked)
    assert r["criteria"]["A"]["evidence"] == 10.0 and r["criteria"]["B"]["evidence"] == 2.5
    assert r["totals"] == {"A": 8.8, "B": 4.0}
    assert r["winner"] == "A" and r["would_have_chosen"] == "A" and r["text_matches_scores"] is True
    # 0.5 * min(1, 5.3 / 3) + 0.3 * 1 + 0.2 * (2 of 3 A claims cited)
    assert r["confidence"] == round(0.5 + 0.3 + 0.2 * 2 / 3, 2)


def test_the_same_labels_always_give_the_same_verdict():
    one = score_rubric(rubric(ALL_OK), CLAIMS, STATS)
    two = score_rubric(rubric(dict(reversed(list(ALL_OK.items())))), CLAIMS, STATS)
    assert one == two


def test_a_small_lead_is_no_clear_winner_and_confidence_is_capped():
    checks = {"A1": "supported", "A2": "supported", "A3": "uncited", "B1": "supported", "B2": "supported"}
    r = score_rubric(rubric(checks, a=(6, 6, 6), b=(6, 6, 6), leaning="none"), CLAIMS, STATS)
    assert r["gap"] == 0 and r["winner"] == "none" and r["text_matches_scores"] is True
    assert r["confidence"] <= 0.5


def test_a_lead_exactly_at_the_margin_wins():
    checks = {"A1": "supported", "A2": "supported", "A3": "uncited", "B1": "supported", "B2": "supported"}
    # evidence equal (10 each); scope/engagement differ so the totals differ by exactly 1.0
    r = score_rubric(rubric(checks, a=(8, 8, 5), b=(4, 4, 5), leaning="A"), CLAIMS, STATS)
    assert r["gap"] == 2.0
    assert r["winner"] == "A"
    r2 = score_rubric(rubric(checks, a=(8, 8, 5), b=(7.5, 7.5, 5), leaning="none"), CLAIMS, STATS)
    assert r2["gap"] == 0.25 and r2["winner"] == "none"
    r3 = score_rubric(rubric(checks, a=(8, 8, 5), b=(7, 7, 5), leaning="A"), CLAIMS, STATS)
    assert r3["gap"] == 0.5 and r3["winner"] == "A"  # a lead exactly at the margin wins, with low confidence
    assert r3["confidence"] < 0.7


def test_an_uncited_claim_cannot_be_supported_even_if_the_model_says_so():
    checks = dict(ALL_OK, A3="supported")
    r = score_rubric(rubric(checks), CLAIMS, STATS)
    assert r["claim_counts"]["A"] == {"supported": 2, "partly_supported": 0, "unsupported": 0, "uncited": 1}


def test_unknown_duplicate_and_bad_labels_are_ignored_and_coverage_reflects_it():
    rb = rubric({"A1": "supported", "ZZ9": "supported"})
    rb["claim_checks"] += [{"claim": "A1", "label": "unsupported", "reason": "dup"}, {"claim": "B1", "label": "great", "reason": "x"}]
    r = score_rubric(rb, CLAIMS, STATS)
    assert r["claim_counts"]["A"]["supported"] == 1 and r["claim_counts"]["A"]["unsupported"] == 0
    assert r["coverage"] == 0.2


def test_missing_criteria_for_a_side_means_no_winner_and_zero_confidence():
    rb = rubric(ALL_OK)
    rb["criteria"] = rb["criteria"][:1]
    r = score_rubric(rb, CLAIMS, STATS)
    assert r["complete"] is False and r["winner"] == "none" and r["confidence"] == 0.0


def test_fake_citations_lower_confidence():
    bad = {"A": {"total": 3, "unverified": 3}, "B": {"total": 2, "unverified": 2}}
    good = score_rubric(rubric(ALL_OK), CLAIMS, STATS)["confidence"]
    assert score_rubric(rubric(ALL_OK), CLAIMS, bad)["confidence"] < good


def test_a_user_pick_keeps_what_the_judge_would_have_chosen():
    r = score_rubric(rubric(ALL_OK), CLAIMS, STATS, fixed_label="B")
    assert r["winner"] == "B" and r["would_have_chosen"] == "A"


def test_scores_are_clamped_to_zero_through_ten():
    r = score_rubric(rubric(ALL_OK, a=(99, -4, "x")), CLAIMS, STATS)
    assert r["criteria"]["A"]["scope"] == 10.0 and r["criteria"]["A"]["engagement"] == 0.0 and r["criteria"]["A"]["fidelity"] == 0.0


class RubricBrain(ScriptedBrain):
    def __init__(self, leaning="A", b_better=False, **kw):
        super().__init__(**kw)
        self.leaning, self.b_better = leaning, b_better

    async def judge(self, view, fixed_winner):
        self.judge_views.append(view)
        hi, lo = (8, 4)
        a, b = (lo, hi) if self.b_better else (hi, lo)
        checks = [{"claim": c, "label": "supported" if i["cited"] else "uncited", "reason": "r"} for c, i in view.claims.items()]
        return JudgeVerdict(
            winner=self.leaning, would_have_chosen=self.leaning, confidence=0.99, rationale="r", summary="s", final_output="Text.",
            scores={}, strongest_counterpoints=["c"], verdict_flips_if=["f"],
            rubric={"claim_checks": checks, "leaning": self.leaning, "criteria": [
                {"position": "A", "scope": a, "engagement": a, "fidelity": a, "note": "Position A is tidy"},
                {"position": "B", "scope": b, "engagement": b, "fidelity": b, "note": "Position B is loose"}]},
        )


def test_graph_uses_the_computed_winner_and_confidence_not_the_models():
    brain = RubricBrain(leaning="A")
    values, _, _ = run(drive(make_deps(brain, seed=3), rounds=1))
    v = values["verdict"]
    a_side = values["ab_map"]["A"]
    assert v["winner_side"] == a_side and v["confidence"] != 0.99
    assert set(v["scores"]) >= {"for", "against", "rubric"}
    assert v["scores"]["rubric"]["totals"][a_side] > v["scores"]["rubric"]["totals"]["for" if a_side == "against" else "against"]
    assert "rubric" not in v
    assert not v["final_output"].startswith("**")


def test_graph_warns_when_the_judges_leaning_disagrees_with_its_own_totals():
    """No independent check available (this brain has none), so the totals still decide and the reader is warned."""
    brain = RubricBrain(leaning="A", b_better=True)
    values, _, _ = run(drive(make_deps(brain, seed=3), rounds=1))
    v = values["verdict"]
    assert v["winner_side"] == values["ab_map"]["B"]
    assert v["final_output"].startswith("**Treat this verdict with caution.**")
    assert v["scores"]["rubric"]["text_matches_scores"] is False


def test_rubric_notes_are_stored_with_real_side_names_not_position_letters():
    brain = RubricBrain(leaning="A")
    values, _, _ = run(drive(make_deps(brain, seed=3), rounds=1))
    notes = values["verdict"]["scores"]["rubric"]["notes"]
    assert set(notes) == {"for", "against"}
    assert not any("Position" in n for n in notes.values())


def test_prompts_carry_the_v41_rules():
    from debate import prompts
    sys_prompt = prompts.debater_system()
    assert "exactly as worded" in sys_prompt and "'valid'" in sys_prompt
    assert "stand on its own" in prompts.FRAME_SYSTEM and "net result" in prompts.FRAME_SYSTEM


# ---------------------------------------------------------------- several judge samples, combined in code
import re

import pytest

from debate.fakes import tok
from debate.scoring import combine_samples, sample_to_sides


def _sample(for_scope=8, against_scope=5, ab=None, leaning_side=None):
    ab = ab or {"A": "for", "B": "against"}
    lab = {s: l for l, s in ab.items()}
    a_pos, b_pos = (for_scope, against_scope) if ab["A"] == "for" else (against_scope, for_scope)
    claims = {"A1": {"label": "A", "cited": True}, "B1": {"label": "B", "cited": True}}
    stats = {"A": {"total": 1, "unverified": 0}, "B": {"total": 1, "unverified": 0}}
    rb = {
        "claim_checks": [{"claim": "A1", "label": "supported", "reason": "r"}, {"claim": "B1", "label": "supported", "reason": "r"}],
        "criteria": [
            {"position": "A", "scope": a_pos, "engagement": a_pos, "fidelity": a_pos, "note": "n"},
            {"position": "B", "scope": b_pos, "engagement": b_pos, "fidelity": b_pos, "note": "n"},
        ],
        "leaning": "A" if (leaning_side or "for") == ab["A"] else "B",
    }
    return sample_to_sides(score_rubric(rb, claims, stats), ab)


def test_one_sample_combines_to_exactly_the_single_call_result():
    s = _sample()
    c = combine_samples([s])
    direct = score_rubric(
        {"claim_checks": [{"claim": "A1", "label": "supported"}, {"claim": "B1", "label": "supported"}],
         "criteria": [{"position": "A", "scope": 8, "engagement": 8, "fidelity": 8}, {"position": "B", "scope": 5, "engagement": 5, "fidelity": 5}],
         "leaning": "A"},
        {"A1": {"label": "A", "cited": True}, "B1": {"label": "B", "cited": True}},
        {"A": {"total": 1, "unverified": 0}, "B": {"total": 1, "unverified": 0}},
    )
    assert c["judged"] == "for" and c["totals"] == {"for": direct["totals"]["A"], "against": direct["totals"]["B"]}
    assert c["confidence"] == direct["confidence"] and c["agreement"] == 1.0 and c["samples"] == 1


def test_the_middle_sample_wins_over_one_noisy_outlier():
    samples = [_sample(8, 5), _sample(8, 5, ab={"A": "against", "B": "for"}), _sample(3, 9)]  # the third one is an outlier
    c = combine_samples(samples)
    assert c["judged"] == "for"
    assert c["samples"] == 3 and c["agreement"] == pytest.approx(0.67, abs=0.01)
    assert c["gap_spread"] > 0
    assert samples[c["writer"]]["judged"] == "for", "the sample that writes the prose must agree with the combined winner"


def test_disagreement_lowers_confidence_and_a_flip_in_a_close_case_gives_no_winner():
    agree = combine_samples([_sample(8, 5)] * 3)
    split = combine_samples([_sample(8, 5), _sample(8, 5), _sample(5, 8)])
    assert split["judged"] == "for" and split["confidence"] < agree["confidence"]
    tie = combine_samples([_sample(8, 5), _sample(5, 8)])  # mean of the two: no lead at all
    assert tie["judged"] == "none" and tie["confidence"] <= 0.5


def test_swapped_labels_give_the_same_combined_result():
    a = combine_samples([_sample(8, 5, ab={"A": "for", "B": "against"})])
    b = combine_samples([_sample(8, 5, ab={"A": "against", "B": "for"})])
    assert a["totals"] == b["totals"] and a["judged"] == b["judged"] == "for"


def test_incomplete_samples_are_ignored_when_a_complete_one_exists():
    good = _sample()
    bad = dict(_sample(1, 9), complete=False)
    c = combine_samples([bad, good])
    assert c["judged"] == "for" and c["complete"] is True and c["samples"] == 1


def test_no_samples_is_an_error():
    with pytest.raises(ValueError):
        combine_samples([])


# ---------------------------------------------------------------- through the graph
class SampledRubricBrain(ScriptedBrain):
    """A judge that reads the transcript's text to find which label is FOR, and scores FOR higher. `plan` gives each
    call's (for_score, against_score); calls beyond the plan reuse the last entry."""

    def __init__(self, plan, fail=()):
        super().__init__()
        self.plan = plan
        self.fail = set(fail)
        self.calls = 0

    async def judge(self, view, fixed_winner, sink=None):
        i = self.calls
        self.calls += 1
        if i in self.fail:
            raise RuntimeError("judge sample failed")
        base = await super().judge(view, fixed_winner, sink if i == 0 else None)
        for_label = re.search(r"\[Position ([AB]) \|[^\]]*\]\nargument " + tok("for"), view.rendered).group(1)
        f, a = self.plan[min(i, len(self.plan) - 1)]
        checks = [{"claim": cid, "label": "supported", "reason": "r"} for cid in view.claims]
        crit = [{"position": p, "scope": (f if p == for_label else a), "engagement": (f if p == for_label else a),
                 "fidelity": (f if p == for_label else a), "note": "n"} for p in ("A", "B")]
        return base.model_copy(update={"rubric": {"claim_checks": checks, "criteria": crit, "leaning": for_label if f > a else "none"}})


def _judged(plan, samples, fail=(), seed=1):
    brain = SampledRubricBrain(plan, fail)
    deps = make_deps(brain, seed=seed, judge_samples=samples)
    values, _, _ = run(drive(deps, rounds=1))
    return brain, values["verdict"]


def test_graph_runs_the_judge_n_times_with_labels_swapped_and_reports_agreement():
    brain, v = _judged([(8, 5)], samples=4)
    assert brain.calls == 4
    first_labels = [re.search(r"\[Position ([AB]) \|[^\]]*\]\nargument " + tok("for"), w.rendered).group(1) for w in brain.judge_views]
    assert first_labels[0] != first_labels[1] and first_labels[0] == first_labels[2], first_labels
    assert v["winner_side"] == "for"
    r = v["scores"]["rubric"]
    assert r["judge_samples"] == 4 and r["agreement"] == 1.0 and r["text_matches_scores"] is True
    assert r["totals"]["for"] > r["totals"]["against"]


def test_graph_one_noisy_sample_does_not_flip_the_winner():
    _, v = _judged([(8, 5), (8, 5), (4, 8)], samples=3)
    assert v["winner_side"] == "for"
    assert v["scores"]["rubric"]["agreement"] < 1.0


def test_graph_survives_a_failed_sample_and_fails_only_if_all_fail():
    brain, v = _judged([(8, 5)], samples=3, fail={1})
    assert v["winner_side"] == "for" and v["scores"]["rubric"]["judge_samples"] == 2
    with pytest.raises(Exception):
        _judged([(8, 5)], samples=2, fail={0, 1})


def test_graph_single_sample_matches_the_old_behaviour():
    _, v = _judged([(8, 5)], samples=1)
    assert v["winner_side"] == "for" and v["scores"]["rubric"]["judge_samples"] == 1
    assert v["scores"]["rubric"]["agreement"] == 1.0


# ---------------------------------------------------------------- the prose must agree with the totals
def _with_conclusion(plan, conclusion, samples=3, seed=1):
    brain = SampledRubricBrain(plan)
    brain.conclusion = conclusion
    deps = make_deps(brain, seed=seed, judge_samples=samples)
    values, _, _ = run(drive(deps, rounds=1))
    return brain, values["verdict"]


def test_prose_that_contradicts_the_totals_means_no_winner_is_reported():
    """The shape seen in runs/eval_6b and eval_6c: totals said FOR, the written verdict argued the claim was not
    supported. Showing either as the winner would be a guess dressed as a verdict, so neither is reported."""
    brain, v = _with_conclusion([(8, 5)], conclusion="not_supported")
    r = v["scores"]["rubric"]
    assert v["winner_side"] == "no_clear_winner"
    assert v["would_have_chosen_side"] == "for", "what the totals said is kept, not discarded"
    assert r["prose_conclusion"] == "against" and r["prose_matches_winner"] is False
    assert r["text_matches_scores"] is False
    assert v["confidence"] <= 0.5
    assert v["final_output"].startswith("**No clear winner.**")
    assert "argued for different sides" in v["final_output"]
    assert r["prose_contradicts_winner"] is True


def test_prose_that_agrees_is_not_flagged():
    brain, v = _with_conclusion([(8, 5)], conclusion="supported")
    r = v["scores"]["rubric"]
    assert r["prose_conclusion"] == "for" and r["prose_matches_winner"] is True
    assert r["text_matches_scores"] is True
    assert not v["final_output"].startswith("> Scoring note")


def test_the_check_reads_the_deanonymized_text_and_the_proposition():
    brain, v = _with_conclusion([(8, 5)], conclusion="supported")
    assert len(brain.conclusion_calls) == 1, "one check per debate, not one per judge sample"
    proposition, text = brain.conclusion_calls[0]
    assert proposition == "Choose alpha over beta"
    assert "Position A" not in text and "Position B" not in text, "the check must see what the user sees"


def test_a_brain_without_the_check_still_finishes_and_keeps_the_old_behaviour():
    brain, v = _judged([(8, 5)], samples=2)  # ScriptedBrain.conclusion is None -> method raises
    r = v["scores"]["rubric"]
    assert v["winner_side"] == "for" and r["text_matches_scores"] is True
    assert "prose_conclusion" not in r and not v["final_output"].startswith("> Scoring note")


def test_an_unreadable_check_reply_changes_nothing():
    brain, v = _with_conclusion([(8, 5)], conclusion="unreadable")
    r = v["scores"]["rubric"]
    assert "prose_conclusion" not in r and r["text_matches_scores"] is True


def test_a_verdict_that_reaches_no_conclusion_is_left_as_scored():
    """The judge supplies the analysis and the rubric resolves it, so a non-committal verdict is the normal case, not a
    contradiction. Treating it as one made 4 of 6 open-question debates in runs/eval_topics report no winner."""
    brain, v = _with_conclusion([(8, 5)], conclusion="neither")
    r = v["scores"]["rubric"]
    assert r["prose_conclusion"] == "no_clear_winner"
    assert r["prose_matches_winner"] is False, "it still did not match, and that is recorded"
    assert r["prose_contradicts_winner"] is False, "but it did not argue the other way either"
    assert v["winner_side"] == "for", "the computed winner stands"
    assert r["text_matches_scores"] is True
    assert not v["final_output"].startswith("**")


def test_a_leaning_verdict_over_a_scored_tie_is_also_left_alone():
    """The margin test is deliberately conservative; prose that leans where the totals found no gap is not a conflict."""
    brain, v = _with_conclusion([(6, 6)], conclusion="supported")
    r = v["scores"]["rubric"]
    assert v["winner_side"] == "no_clear_winner" and r["prose_conclusion"] == "for"
    assert r["prose_contradicts_winner"] is False and r["text_matches_scores"] is True
    assert not v["final_output"].startswith("**")


def test_prose_agreement_leaves_the_winner_and_the_text_alone():
    brain, v = _with_conclusion([(8, 5)], conclusion="supported")
    assert v["winner_side"] == "for" and v["confidence"] > 0.5
    assert not v["final_output"].startswith("**")


def test_the_check_is_counted_in_usage():
    brain = SampledRubricBrain([(8, 5)])
    brain.conclusion = "supported"
    brain.usage = Usage(model="m", cost=0.002)
    deps = make_deps(brain, seed=1, judge_samples=1)
    values, _, _ = run(drive(deps, rounds=1))
    phases = [u.get("phase") for u in values["usage"]]
    assert "conclusion_check" in phases
