"""Branches: the questions a finished debate proposes, and what each resulting node is allowed to see."""
import pytest

from debate.branching import assign_ids, branch_chats, context_seed, open_questions, to_rows
from debate.fakes import ScriptedBrain, make_deps
from debate.render import node_title, render_chats
from debate.schemas import Branch, Usage
from tests.helpers import drive, run

VERDICT = """The evidence does not settle it.

**What the evidence supports**
- Microservices allow independent deployment.

**What is still open or conflicting**
Nobody measured delivery speed against operating burden in a startup.

**Caveats**
Abstract-level evidence only.

**Next steps**
- Go and read the full texts.

Strongest points against this conclusion:
- SIBLING-COUNTERPOINT

This would change if:
- SIBLING-ONE happened
- SIBLING-TWO happened"""

PAYLOAD = {
    "proposition": "Day-one microservices beat a monolith for a small startup",
    "winner": "no_clear_winner",
    "summary": "Neither side established its case.",
    "final_output": VERDICT,
    "citations": [{"id": "s2-a", "title": "A helpdesk comparison", "year": 2025}],
}

THREE = [
    Branch(title="Delivery speed vs operating cost",
           question="Do microservices-first startups ship faster once operating burden is counted?",
           why="Nobody measured it.", kind="research", from_claims=["A3"]),
    Branch(title="When independent releases matter",
           question="At what team size do independent releases start to pay for themselves?",
           why="Both sides asserted it without a timeline.", kind="research"),
    Branch(title="Cost of migrating later",
           question="How expensive is decomposing a monolith at year two?",
           why="The sources never compared it with running services from day one.", kind="debate"),
]


# ---------------------------------------------------------------- the seed, which is where leakage would happen
def test_a_branch_seed_never_contains_another_branchs_topic():
    branches = assign_ids(THREE)
    seeds = [context_seed(PAYLOAD, b) for b in branches]
    for i, seed in enumerate(seeds):
        assert branches[i].question in seed, "its own question must be there"
        for j, other in enumerate(branches):
            if i != j:
                assert other.question not in seed, f"branch {i} can see branch {j}'s question"
                assert other.title not in seed, f"branch {i} can see branch {j}'s title"


def test_the_seed_drops_the_sections_that_list_the_directions():
    seed = context_seed(PAYLOAD, assign_ids(THREE)[0])
    for leaked in ("SIBLING-ONE", "SIBLING-TWO", "SIBLING-COUNTERPOINT", "This would change if", "Next steps"):
        assert leaked not in seed, f"{leaked!r} names or implies the other branches"


def test_the_seed_keeps_the_shared_findings_and_the_sources():
    seed = context_seed(PAYLOAD, assign_ids(THREE)[0])
    assert "Microservices allow independent deployment" in seed
    assert "Nobody measured delivery speed against operating burden" in seed
    assert "A helpdesk comparison (2025)" in seed
    assert PAYLOAD["proposition"] in seed
    # The summary restates the verdict, so it is left out when the verdict text is there: a node that opened by
    # making the same point twice read as sloppy.
    assert PAYLOAD["summary"] not in seed


def test_the_summary_stands_in_when_there_is_no_verdict_text():
    payload = {**PAYLOAD, "final_output": ""}
    seed = context_seed(payload, assign_ids(THREE)[0])
    assert payload["summary"] in seed
    assert THREE[0].question in seed
    assert "did not settle it" in seed, "a near-tie must be stated, not implied"


def test_interface_banners_are_not_carried_into_a_branch():
    payload = {**PAYLOAD, "final_output": "**No clear winner.** The scored comparison and the written analysis below "
                                          "argued for different sides.\n\n" + VERDICT}
    seed = context_seed(payload, assign_ids(THREE)[0])
    assert "No clear winner.**" not in seed and "argued for different sides" not in seed


def test_a_leaning_verdict_says_which_way_it_leaned():
    seed = context_seed({**PAYLOAD, "winner": "against"}, assign_ids(THREE)[0])
    assert "leaned AGAINST" in seed


def test_open_questions_pulls_the_unresolved_section():
    assert open_questions(VERDICT).startswith("Nobody measured delivery speed")
    assert open_questions("") == "" and open_questions("no headings here") == ""


def test_branch_chats_are_a_seeded_question_and_reply():
    chats = branch_chats(PAYLOAD, assign_ids(THREE)[0])
    assert [c["role"] for c in chats] == ["user", "assistant"]
    assert chats[0]["content"] == THREE[0].question
    assert chats[1]["content"] == context_seed(PAYLOAD, assign_ids(THREE)[0])
    assert [c["seq"] for c in chats] == [0, 1]


def test_ids_and_rows_carry_the_interface_state():
    rows = to_rows(assign_ids(THREE))
    assert [r["id"] for r in rows] == ["b1", "b2", "b3"]
    assert all(r["selected"] is False and r["created_node_id"] is None for r in rows)
    assert rows[2]["kind"] == "debate"


# ---------------------------------------------------------------- through the graph
def _run(branches, max_branches=5, samples=1):
    brain = ScriptedBrain()
    brain.branches = branches
    brain.usage = Usage(model="m", cost=0.001)
    deps = make_deps(brain, seed=1, judge_samples=samples, max_branches=max_branches)
    values, _, _ = run(drive(deps, rounds=1))
    return brain, deps, values


def test_the_graph_asks_for_branches_and_stores_them_on_the_result():
    brain, deps, values = _run(THREE)
    payload = deps.writer.results["d1"]
    assert [b["id"] for b in payload["branches"]] == ["b1", "b2", "b3"]
    assert payload["branches"][0]["title"] == THREE[0].title
    assert len(brain.branch_calls) == 1, "one branch call per debate"
    call = brain.branch_calls[0]
    assert call["proposition"] == payload["proposition"]


def test_the_branch_call_is_counted_in_usage():
    brain, deps, values = _run(THREE)
    phases = [u.get("phase") for u in deps.writer.results["d1"]["usage"]]
    assert "branches" in phases
    assert deps.writer.results["d1"]["usage_summary"]["total"]["cost"] > 0


def test_max_branches_zero_turns_the_feature_off():
    brain, deps, values = _run(THREE, max_branches=0)
    assert deps.writer.results["d1"]["branches"] == [] and brain.branch_calls == []


def test_max_branches_caps_how_many_come_back():
    brain, deps, values = _run(THREE, max_branches=2)
    assert len(deps.writer.results["d1"]["branches"]) == 2


def test_a_brain_without_branch_support_still_finishes():
    deps = make_deps(ScriptedBrain(), seed=1, judge_samples=1)  # .branches is None -> method raises
    values, _, _ = run(drive(deps, rounds=1))
    assert deps.writer.results["d1"]["branches"] == []
    assert values["verdict"]["winner_side"] in ("for", "against", "no_clear_winner")


def test_a_failing_branch_call_never_fails_the_debate():
    class Boom(ScriptedBrain):
        async def propose_branches(self, *a, **k):
            raise RuntimeError("provider down")
    deps = make_deps(Boom(), seed=1, judge_samples=1)
    values, _, _ = run(drive(deps, rounds=1))
    assert deps.writer.results["d1"]["branches"] == [] and values["result_node_id"]


def test_the_completed_event_says_how_many_branches_there_are():
    brain, deps, values = _run(THREE)
    done = deps.emitter.of("completed")[0]
    assert done["branches"] == 3 and done["node_id"]


# ---------------------------------------------------------------- what the node shows
def test_a_near_tie_is_titled_contested_not_no_clear_winner():
    assert node_title(PAYLOAD, "t").startswith("Contested: ")
    assert "No clear winner" not in node_title(PAYLOAD, "t")


def test_the_node_lists_the_branches_for_ticking():
    payload = {**PAYLOAD, "confidence": 0.45, "rationale": "r", "scores": {},
               "strongest_counterpoints": [], "verdict_flips_if": [], "end_reason": "rounds_exhausted",
               "branches": to_rows(assign_ids(THREE))}
    body = render_chats("t", payload)[1]["content"]
    assert "Where to go next" in body
    for b in THREE:
        assert b.title in body and b.question in body
    assert "find evidence" in body and "worth its own debate" in body
    assert "Genuinely unsettled" in body and "Verdict: no clear winner" not in body
