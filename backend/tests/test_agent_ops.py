"""The agent runtime's rules, without a database or a model: what ops.check lets through, the one-decision-per-step
batch policy, limits, task blocking and the snapshot the model reads. Runs in CI."""
import os

import pytest

_dummies = {"DATABASE_URL": "postgresql://dummy@localhost/dummy", "JWT_SECRET_KEY": "test-secret"}
_added = [k for k in _dummies if k not in os.environ]
os.environ.update({k: _dummies[k] for k in _added})

from app.agent import ops, prompts  # noqa: E402
from app.agent.ops import OpError, State  # noqa: E402

for _k in _added:
    del os.environ[_k]

NODE = "11111111-1111-4111-8111-111111111111"


def run(**kw):
    return {"id": "r", "goal": "Does RL help?", "active_node_id": None, "clarifications": [], "authorized_deletes": [],
            "iteration": 1, "tool_calls": 0, "replans": 0, "pending_input": None, **kw}


def task(key, status="pending", deps=(), **kw):
    return {"key": key, "objective": f"Objective of {key}", "status": status, "depends_on": list(deps),
            "reason": None, "assessment": None, **kw}


def step(name="search_nodes", task_key="t1", status="succeeded", result=None, kind="tool", iteration=1):
    return {"kind": kind, "task_key": task_key, "name": name, "status": status, "iteration": iteration,
            "args": {}, "result": result if result is not None else {"results": [{"node_id": NODE}]}}


def state(tasks=(), steps=(), plan=True, **kw):
    return State(run=run(**kw), plan={"version": 1, "strategy": "s", "assumptions": []} if plan else None,
                 tasks=list(tasks), steps=list(steps))


def rejects(st, name, args, match):
    with pytest.raises(OpError, match=match):
        ops.check(st, name, args)


PLAN = {"strategy": "Compare RL with baselines", "tasks": [{"objective": "Find the baseline approaches"}]}
DONE = {"task_id": "t1", "investigated": "Searched the tree", "findings": "Found one relevant node about RL.",
        "satisfied": True, "needs_more_research": False, "node_refs": [NODE]}


def test_plan_once_and_dependencies_must_exist():
    assert ops.check(state(plan=False), "create_plan", PLAN)
    rejects(state(), "create_plan", PLAN, "already exists")
    rejects(state(plan=False), "create_plan",
            {**PLAN, "tasks": [{"objective": "First task here", "depends_on": ["t2"]}, {"objective": "Second task here"}]},
            "Unknown dependency t2")
    ok = {**PLAN, "tasks": [{"objective": "First task here"}, {"objective": "Second task here", "depends_on": ["t1"]}]}
    assert ops.check(state(plan=False), "create_plan", ok)


def test_bad_arguments_come_back_as_readable_errors():
    rejects(state(plan=False), "create_plan", {"strategy": "x", "tasks": []}, "Bad arguments for create_plan")
    rejects(state(), "request_user_input",
            {"questions": [{"id": "a", "prompt": "Which one?", "type": "single", "options": [{"label": "only"}]}]},
            "at least 2 options")


def test_replans_need_a_reason_and_are_bounded():
    upd = {"strategy": "Add deployment evidence", "reason": "All studies were simulations"}
    assert ops.check(state(), "update_plan", upd)
    rejects(state(), "update_plan", {"strategy": "Add deployment evidence"}, "reason")
    rejects(state(replans=ops.MAX_REPLANS), "update_plan", upd, "replanning limit")
    rejects(state(plan=False), "update_plan", upd, "no plan yet")


def test_task_cap():
    full = [task(f"t{i}") for i in range(1, ops.MAX_TASKS + 1)]
    rejects(state(full), "create_task", {"objective": "One task too many"}, "At most")


def test_cannot_start_a_task_before_its_dependencies_or_two_at_once():
    t = [task("t1"), task("t2", deps=["t1"])]
    rejects(state(t), "update_task", {"task_id": "t2", "status": "in_progress"}, "Dependencies not completed: t1")
    assert ops.check(state([task("t1", "completed"), task("t2", deps=["t1"])]), "update_task",
                     {"task_id": "t2", "status": "in_progress"})
    rejects(state([task("t1", "in_progress"), task("t2")]), "update_task", {"task_id": "t2", "status": "in_progress"},
            "already in progress")


def test_skip_needs_reason_and_completed_tasks_are_immutable():
    rejects(state([task("t1")]), "update_task", {"task_id": "t1", "status": "skipped"}, "reason is required")
    assert ops.check(state([task("t1")]), "update_task", {"task_id": "t1", "status": "skipped", "reason": "irrelevant now"})
    rejects(state([task("t1", "completed")]), "update_task", {"task_id": "t1", "objective": "Rewrite the objective"},
            "cannot be changed")
    # completion is not a status the model can set
    rejects(state([task("t1", "in_progress")]), "update_task", {"task_id": "t1", "status": "completed"}, "Bad arguments")


def test_complete_task_needs_an_in_progress_task_a_real_result_and_real_references():
    working = state([task("t1", "in_progress")], [step()])
    assert ops.check(working, "complete_task", DONE)
    rejects(state([task("t1")], [step()]), "complete_task", DONE, "start it with update_task")
    rejects(state([task("t1", "in_progress")]), "complete_task", DONE, "No successful research call")
    rejects(state([task("t1", "in_progress")], [step(status="failed", result={"error": "x"})]), "complete_task", DONE,
            "No successful research call")
    rejects(state([task("t1", "in_progress")], [step(task_key="t2")]), "complete_task", DONE, "No successful research call")
    rejects(working, "complete_task", {**DONE, "node_refs": ["22222222-2222-4222-8222-222222222222"]}, "never appeared")
    rejects(working, "complete_task", {**DONE, "source_refs": ["p9:c1"]}, "never appeared")
    cited = state([task("t1", "in_progress")], [step(name="search_sources", result={"passages": [{"evidence_id": "p9:c1"}]})])
    assert ops.check(cited, "complete_task", {**DONE, "node_refs": [], "source_refs": ["P9:C1"]})


def test_finish_requires_closed_tasks_and_an_honest_outcome():
    fin = {"outcome": "satisfied", "summary": "RL helped in simulations; deployment evidence is missing.", "evidence": [NODE]}
    done = [task("t1", "completed")]
    ev = [step()]
    assert ops.check(state(done, ev), "finish_research", fin)
    rejects(state([task("t1", "completed"), task("t2")], ev), "finish_research", fin, "Tasks still open: t2")
    rejects(state([task("t1", "skipped", reason="x")], ev), "finish_research", fin, "only be inconclusive")
    assert ops.check(state([task("t1", "skipped", reason="x")], ev), "finish_research", {**fin, "outcome": "inconclusive"})
    rejects(state(done, ev), "finish_research", {**fin, "outcome": "blocked"}, "blocked needs")
    assert ops.check(state([*done, task("t2", "failed")], ev), "finish_research", {**fin, "outcome": "blocked"})
    rejects(state(done, []), "finish_research", fin, "never appeared")


def test_only_one_question_at_a_time():
    q = {"questions": [{"id": "scope", "prompt": "Which scope?", "type": "single",
                        "options": [{"label": "Narrow"}, {"label": "Broad"}]}]}
    assert ops.check(state(), "request_user_input", q)
    rejects(state(pending_input={"kind": "agent"}), "request_user_input", q, "already pending")


def test_failed_or_skipped_dependencies_block_and_unblock_dependents():
    ts = [task("t1", "failed"), task("t2", deps=["t1"]), task("t3")]
    assert ops.blocked_changes(ts) == [("t2", "blocked", "dependency t1 is failed")]
    ts = [task("t1", "skipped"), task("t2", "blocked", deps=["t1"])]
    assert ops.blocked_changes(ts) == []
    ts = [task("t1", "pending"), task("t2", "blocked", deps=["t1"])]
    assert ops.blocked_changes(ts) == [("t2", "pending", None)]


def test_one_decision_per_step():
    assert ops.batch_error(["create_plan"]) is None
    assert ops.batch_error(["write_node"]) is None
    assert ops.batch_error(["search_nodes", "get_node", "web_search"]) is None
    assert "plain text" in ops.batch_error([])
    assert "Unknown tool" in ops.batch_error(["rm_rf"])
    assert "read-only" in ops.batch_error(["search_nodes", "write_node"])
    assert "read-only" in ops.batch_error(["create_task", "create_task"])
    assert "At most" in ops.batch_error(["search_nodes"] * (ops.MAX_BATCH + 1))


def test_limits():
    assert ops.limit_reached(run()) is None
    assert "step limit" in ops.limit_reached(run(iteration=ops.MAX_ITERATIONS))
    assert "tool-call budget" in ops.limit_reached(run(tool_calls=ops.MAX_TOOL_CALLS))


def test_tool_lists_are_plain_and_complete():
    names = {t["function"]["name"] for t in ops.ALL_TOOLS}
    assert names == ops.OPS | ops.READ_ONLY | ops.MUTATING
    assert "$ref" not in str(ops.ORCH_TOOLS) and "anyOf" not in str(ops.ORCH_TOOLS)


def test_snapshot_gives_goal_budget_plan_and_recent_results_not_the_tree():
    done = task("t1", "completed", assessment={"findings": "RL beat baselines in simulation.", "node_refs": [NODE],
                                               "source_refs": ["p9:c1"], "satisfied": True, "unresolved": ["real-world?"]})
    st = state([done, task("t2", deps=["t1"], status="blocked", reason="dependency t1 is failed")],
               [step(iteration=1, result={"big": "x" * 5000}), step(iteration=2, status="unknown", result={"error": "?"})],
               iteration=2, clarifications=[{"question": "Scope?", "answer": "Narrow"}], authorized_deletes=[NODE])
    text = prompts.snapshot(st)
    for needle in ("GOAL (unchanged): Does RL help?", "Scope? -> Narrow", f"deleting these nodes: {NODE}", f"step 2/{ops.MAX_ITERATIONS}",
                   "PLAN v1", "t1 [completed]", "t2 [blocked] (after t1)", "RL beat baselines", "real-world?",
                   "OUTCOME UNKNOWN"):
        assert needle in text
    assert "more chars" in text  # the older step's 5000-char result is squeezed
    assert "{replans}" not in prompts.system_prompt()


URL = "https://www.nrc.gov/reactors/new-reactors/microreactors.html"


def test_web_urls_from_search_results_can_be_cited():
    web = state([task("t1", "in_progress")],
                [step(name="web_search", result={"results": [{"title": "NRC", "url": URL, "snippet": "Part 57"}]})])
    assert ops.check(web, "complete_task", {**DONE, "node_refs": [], "source_refs": [URL.upper()]})
    rejects(web, "complete_task", {**DONE, "node_refs": [], "source_refs": ["https://example.com/never-seen"]}, "never appeared")


def test_the_agents_own_written_nodes_are_not_evidence_for_its_conclusion():
    fin = {"outcome": "partially_satisfied", "summary": "RL looks promising in simulation, deployment evidence is thin.",
           "evidence": [NODE]}
    wrote = state([task("t1", "completed")], [step(name="write_node", result={"node_id": NODE})])
    rejects(wrote, "finish_research", fin, "never appeared")
    # the node it wrote can still back a task's findings, and a node it read can back the conclusion
    assert ops.check(state([task("t1", "in_progress")], [step(name="write_node", result={"node_id": NODE})]),
                     "complete_task", DONE)
    assert ops.check(state([task("t1", "completed")], [step()]), "finish_research", fin)


def test_rejected_steps_are_counted_over_the_whole_run():
    rejected = [step(kind="op", status="failed", result={"error": "x"}) for _ in range(5)]
    mixed = [*rejected, step(kind="op"), step(status="failed", result={"error": "y"})]
    assert ops.invalid_total(state(steps=mixed)) == 5
    assert ops.invalid_total(state()) == 0


def test_an_unfinished_task_blocks_what_depends_on_it():
    assert ops.blocked_changes([task("t1", "unfinished"), task("t2", deps=["t1"])]) == [("t2", "blocked", "dependency t1 is unfinished")]


def test_snapshot_warns_when_the_budget_is_low_and_lists_what_the_agent_wrote():
    plenty = prompts.snapshot(state(iteration=5))
    assert "LOW BUDGET" not in plenty and "NODES YOU WROTE" not in plenty
    wrote = step(name="write_node", result={"node_id": NODE})
    wrote["args"] = {"parent_id": "p", "title": "Regulatory viability", "body": "Part 57 is a proposed rule.\nIt may shrink the EPZ."}
    low = prompts.snapshot(state([task("t1", "in_progress")], [wrote], iteration=ops.MAX_ITERATIONS - 3))
    assert "LOW BUDGET: 3 steps" in low and "finish_research" in low
    assert f"{NODE}: Regulatory viability | Part 57 is a proposed rule. It may shrink the EPZ." in low
    assert "LOW BUDGET" in prompts.snapshot(state(tool_calls=ops.MAX_TOOL_CALLS - 2))


def test_research_needs_a_task_in_progress_once_there_is_a_plan():
    pending = state([task("t1"), task("t2", deps=["t1"])])
    assert ops.startable(pending) == ["t1"]
    assert "Start one with update_task" in ops.needs_task(pending, ["search_nodes"]) and "t1" in ops.needs_task(pending, ["write_node"])
    assert ops.needs_task(pending, ["web_search", "get_node"]) is not None
    # operations are not research, and nothing is refused without a plan, with a task under way, or with nothing left to start
    assert ops.needs_task(pending, ["update_task"]) is None
    assert ops.needs_task(state(plan=False), ["search_nodes"]) is None
    assert ops.needs_task(state([task("t1", "in_progress"), task("t2")]), ["search_nodes"]) is None
    assert ops.needs_task(state([task("t1", "completed"), task("t2", "skipped", reason="x")]), ["write_node"]) is None
    assert ops.needs_task(state([task("t1", "failed"), task("t2", "blocked", deps=["t1"])]), ["search_nodes"]) is None


def test_snapshot_points_at_the_tasks_that_can_start():
    assert "NEXT: no task is in progress" in prompts.snapshot(state([task("t1"), task("t2", deps=["t1"])]))
    assert "t1" in prompts.snapshot(state([task("t1")])).split("NEXT:")[1]
    assert "NEXT:" not in prompts.snapshot(state([task("t1", "in_progress")]))
    assert "NEXT:" not in prompts.snapshot(state(plan=False))


def test_a_task_that_builds_on_completed_tasks_can_be_completed_without_new_research():
    synth = state([task("t1", "completed"), task("t2", "in_progress", deps=["t1"])])  # no tool call in t2
    assert ops.check(synth, "complete_task", {**DONE, "task_id": "t2", "node_refs": []})
    # without dependencies it still needs a research call, and the error says how to mark a synthesis task
    alone = state([task("t2", "in_progress")])
    with pytest.raises(OpError, match="depend on them"):
        ops.check(alone, "complete_task", {**DONE, "task_id": "t2", "node_refs": []})
    # citations are still checked against what the run retrieved
    rejects(synth, "complete_task", {**DONE, "task_id": "t2", "node_refs": [NODE]}, "never appeared")


def test_snapshot_tells_a_dependent_task_to_use_earlier_findings():
    done = task("t1", "completed", assessment={"findings": "Solar costs X.", "node_refs": [], "source_refs": [], "satisfied": True, "unresolved": []})
    text = prompts.snapshot(state([done, task("t2", "in_progress", deps=["t1"])]))
    assert "NOTE: t2 builds on t1" in text and "do not search again" in text
    assert "NOTE:" not in prompts.snapshot(state([task("t1", "in_progress")]))


def test_asking_for_the_status_a_task_already_has_is_not_an_error():
    live = state([task("t1", "completed"), task("t2", "completed"), task("t3", "in_progress")])
    # the exact call that was rejected in a live run: re-stating in_progress while adding the dependencies
    assert ops.check(live, "update_task", {"task_id": "t3", "status": "in_progress", "depends_on": ["t1", "t2"]})
    assert ops.check(live, "update_task", {"task_id": "t3", "status": "in_progress"})
    # a real start is still checked, and so are dependencies added to a task under way
    rejects(state([task("t1"), task("t2", "skipped", reason="x")]), "update_task", {"task_id": "t2", "status": "in_progress"}, "only a pending task")
    rejects(state([task("t1"), task("t2", "in_progress")]), "update_task", {"task_id": "t2", "depends_on": ["t1"]}, "Dependencies not completed: t1")


def test_get_research_state_says_what_to_do_next():
    assert "create_plan" in ops.next_hint(state(plan=False))
    assert "start one with update_task" in ops.next_hint(state([task("t1"), task("t2", deps=["t1"])])) and "t1" in ops.next_hint(state([task("t1")]))
    assert "research it" in ops.next_hint(state([task("t1", "in_progress")]))
    assert "can be completed" in ops.next_hint(state([task("t1", "in_progress")], [step()]))
    assert "can be completed" in ops.next_hint(state([task("t1", "completed"), task("t2", "in_progress", deps=["t1"])]))
    assert "finish_research" in ops.next_hint(state([task("t1", "completed")]))
