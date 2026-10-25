from debate.fakes import ScriptedBrain, make_deps
from debate.schemas import JudgeVerdict
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
    assert not v["final_output"].startswith("> Scoring note")


def test_graph_flags_text_that_disagrees_with_the_rubric():
    brain = RubricBrain(leaning="A", b_better=True)
    values, _, _ = run(drive(make_deps(brain, seed=3), rounds=1))
    v = values["verdict"]
    assert v["winner_side"] == values["ab_map"]["B"]
    assert v["final_output"].startswith("> Scoring note")
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