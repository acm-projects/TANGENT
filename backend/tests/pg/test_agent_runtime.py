"""The agent runtime against a real Postgres (TEST_PG_ADMIN_URL, like the rest of tests/pg). The model and the
research tools are scripted; everything else is real: store, rules, loop, worker claim, events.

test_autonomous_run is the acceptance scenario of the orchestration spec: plan -> investigate -> insufficient evidence
-> replan with a new task -> ask the user (the run pauses) -> answer (it resumes with its state) -> finish with evidence."""
import asyncio
import json
import os
import uuid

import psycopg
import pytest

# app.database refuses to import without these; removed again after (see test_agent_router.py)
_dummies = {"DATABASE_URL": "postgresql://dummy@localhost/dummy", "JWT_SECRET_KEY": "test-secret"}
_added = [k for k in _dummies if k not in os.environ]
os.environ.update({k: _dummies[k] for k in _added})

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

from app import database  # noqa: E402
from app.agent import loop, ops, store, worker  # noqa: E402
from app.agent.schema import AGENT_DDL  # noqa: E402
from conftest import ADMIN  # noqa: E402

for _k in _added:
    del os.environ[_k]


pytestmark = pytest.mark.skipif(not ADMIN, reason="set TEST_PG_ADMIN_URL (a superuser URL to a scratch Postgres)")


def run(coro):
    return asyncio.run(coro)


def tc(name, **args):
    return [{"id": "c", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}]


class Scratch:
    """A throwaway database holding only what the agent tables reference (users, projects) plus the agent tables."""

    def __init__(self):
        self.name = "tangent_agent_" + uuid.uuid4().hex[:10]
        with psycopg.connect(ADMIN, autocommit=True) as c:
            c.execute(f"CREATE DATABASE {self.name}")
        self.admin_url = ADMIN.rpartition("/")[0] + "/" + self.name
        self.sql("CREATE TABLE users (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), email text)")
        self.sql("CREATE TABLE projects (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), created_by_id uuid NOT NULL REFERENCES users(id))")
        for statement in AGENT_DDL:
            self.sql(statement)

    def sql(self, q, params=None):
        with psycopg.connect(self.admin_url, autocommit=True) as c:
            cur = c.execute(q, params)
            return cur.fetchall() if cur.description else None

    def drop(self):
        with psycopg.connect(ADMIN, autocommit=True) as c:
            c.execute(f"DROP DATABASE {self.name} WITH (FORCE)")


class Rt:
    """One scratch database with the agent tables, a scripted model and scripted tools."""

    def __init__(self, pg, monkeypatch):
        user = pg.sql("INSERT INTO users (email) VALUES ('a@x.test') RETURNING id")[0][0]
        project = pg.sql("INSERT INTO projects (created_by_id) VALUES (%s) RETURNING id", (user,))[0][0]
        self.pg, self.ids = pg, {"user": str(user), "project": str(project), "nodes": [str(uuid.uuid4())]}
        self.node = self.ids["nodes"][0]
        self.script, self.requests, self.tool_calls = [], [], []
        self.tool_results = {
            "search_nodes": {"results": [{"node_id": self.node, "title": "Baselines"}]},
            "search_sources": {"passages": [{"evidence_id": "p9:c1", "text": "Clinical network reliability fell."}]},
            "delete_node": {"ok": True, "deleted_node_ids": [self.node]},
            "write_node": {"node_id": self.node},
        }
        url = pg.admin_url.replace("postgresql://", "postgresql+asyncpg://")
        engine = create_async_engine(url, poolclass=NullPool, connect_args={"statement_cache_size": 0})
        monkeypatch.setattr(database, "AsyncSessionLocal", async_sessionmaker(engine, expire_on_commit=False))
        monkeypatch.setattr(worker.loop, "LLM_ATTEMPTS", 1)

        async def fake_stream(messages, model, transport=None, tools=None, tool_choice=None):
            self.requests.append({"messages": messages, "tools": tools, "tool_choice": tool_choice})
            turn = self.script.pop(0)
            if callable(turn):
                turn = await turn()
            yield ({"tool_calls": turn} if isinstance(turn, list) else {"text": turn})

        async def fake_call(name, args, project_id, user_id, model=None, node_id=None):
            self.tool_calls.append((name, args))
            return self.tool_results.get(name, {"error": "no fake for " + name})

        monkeypatch.setattr(loop, "stream_openrouter", fake_stream)
        monkeypatch.setattr(loop.executor.tools, "call_tool", fake_call)

    def start(self, goal="Does RL improve healthcare sensor-network prioritization?") -> str:
        return run(store.create_run(self.ids["project"], self.ids["user"], "m/model", goal, None))

    def drive(self) -> bool:
        return run(worker.run_once())

    def row(self, rid, col="status"):
        return self.pg.sql(f"SELECT {col} FROM agent_runs WHERE id = %s", (rid,))[0][0]

    def types(self, rid):
        return [r[0] for r in self.pg.sql("SELECT type FROM agent_events WHERE run_id = %s ORDER BY id", (rid,))]

    def executions(self, rid, status=None, kind=None):
        rows = self.pg.sql("SELECT name, status, kind, result FROM agent_executions WHERE run_id = %s ORDER BY id", (rid,))
        return [r for r in rows if status in (None, r[1]) and kind in (None, r[2])]


@pytest.fixture
def rt(monkeypatch):
    scratch = Scratch()
    yield Rt(scratch, monkeypatch)
    scratch.drop()


def test_autonomous_run(rt):
    rid, node = rt.start(), rt.node
    rt.script += [
        tc("create_plan", strategy="Compare RL against conventional methods", assumptions=["Papers are in the sources"],
           tasks=[{"objective": "Find baseline approaches"}, {"objective": "Compare latency across studies", "depends_on": ["t1"]}]),
        tc("complete_task", task_id="t1", investigated="Nothing yet", satisfied=True, needs_more_research=False,
           findings="Claimed done before the task was ever started."),  # rejected by the runtime
        tc("update_task", task_id="t1", status="in_progress"),
        tc("search_nodes", query="baseline"),
        tc("complete_task", task_id="t1", investigated="Searched the tree for baselines", node_refs=[node],
           findings="One node covers baselines, but every study found was simulated.", satisfied=False,
           unresolved=["real-world evidence"], needs_more_research=True),
        tc("update_plan", strategy="Add real-world deployment evidence before comparing",
           reason="All studies found were simulated networks", add_tasks=[{"objective": "Investigate deployment limitations", "depends_on": ["t1"]}]),
        tc("request_user_input", questions=[{"id": "scope", "prompt": "Include non-peer-reviewed reports?", "type": "single",
                                             "options": [{"label": "Yes"}, {"label": "No"}]}]),
        # ---- the run pauses here until the user answers ----
        tc("update_task", task_id="t3", status="in_progress"),
        tc("search_sources", query="deployment reliability"),
        tc("complete_task", task_id="t3", investigated="Searched the sources for deployments", source_refs=["p9:c1"],
           findings="One clinical study reports reliability problems after deployment.", satisfied=True, needs_more_research=False),
        tc("update_task", task_id="t2", status="skipped", reason="Superseded by the deployment evidence"),
        tc("finish_research", outcome="partially_satisfied", evidence=[node, "p9:c1"],
           summary="RL looks promising in simulation, but deployment evidence is thin and comparison is inconclusive.",
           limitations=["Only one deployment study"], unresolved_questions=["Real-world latency"]),
    ]
    assert rt.drive()
    assert rt.row(rid) == "waiting_input"
    pending = rt.row(rid, "pending_input")
    assert pending["kind"] == "agent" and pending["questions"][0]["id"] == "scope"
    assert (rt.row(rid, "plan_version"), rt.row(rid, "replans"), rt.row(rid, "invalid_streak")) == (2, 1, 0)
    assert [(e[0], e[1]) for e in rt.executions(rid, kind="op", status="failed")] == [("complete_task", "failed")]
    assert not rt.drive()  # nothing to claim while it waits

    with pytest.raises(store.AnswerError):
        run(store.submit_answer(rid, {"scope": "Maybe"}))
    with pytest.raises(store.AnswerError):
        run(store.submit_answer(rid, {}))
    run(store.submit_answer(rid, {"scope": "No"}))
    assert rt.row(rid) == "queued"
    assert rt.drive()

    assert rt.row(rid) == "completed" and rt.row(rid, "outcome") == "partially_satisfied"
    assert rt.row(rid, "final")["evidence"] == [node, "p9:c1"]
    assert rt.types(rid) == [
        "run.created", "run.started", "plan.created", "task.created", "task.created", "task.started", "tool.executed",
        "task.completed", "plan.revised", "task.created", "input.requested", "input.answered", "task.started",
        "tool.executed", "task.completed", "task.skipped", "run.completed"]
    assert [t[0] for t in rt.tool_calls] == ["search_nodes", "search_sources"]
    # the model got the compact state, with the answer and the revised plan, after the pause
    resumed = rt.requests[7]["messages"][1]["content"]
    assert "Include non-peer-reviewed reports? -> No" in resumed and "PLAN v2" in resumed and "t3 [pending]" in resumed
    assert "GOAL (unchanged): Does RL improve" in resumed
    assert pg_count(rt, "agent_llm_calls", rid) == 12 and not rt.script


def pg_count(rt, table, rid):
    return rt.pg.sql(f"SELECT count(*) FROM {table} WHERE run_id = %s", (rid,))[0][0]


def test_events_replay_from_a_cursor(rt):
    rid = rt.start()
    first = run(store.read_events(rid, 0))[0]
    assert [e["type"] for e in first] == ["run.created"]
    rt.script += [tc("create_plan", strategy="A plan that is long enough", tasks=[{"objective": "Investigate something"}]),
                  tc("update_task", task_id="t1", status="skipped", reason="not needed"),
                  tc("finish_research", outcome="inconclusive", summary="Nothing was investigated, so nothing can be said.")]
    rt.drive()
    events, status = run(store.read_events(rid, first[-1]["id"]))
    assert status == "completed" and events[-1]["type"] == "run.completed"
    assert [e["type"] for e in events[:3]] == ["run.started", "plan.created", "task.created"]
    assert run(store.read_events(rid, events[-1]["id"])) == ([], "completed")


def test_a_write_in_flight_at_a_crash_is_unknown_and_a_read_is_rerun(rt):
    rid = rt.start()
    rt.pg.sql("UPDATE agent_runs SET status = 'running', iteration = 1, locked_at = now() - interval '1 hour' WHERE id = %s", (rid,))
    for i, name in enumerate(("search_nodes", "write_node")):
        rt.pg.sql("INSERT INTO agent_executions (run_id, iteration, call_index, kind, name, args, idempotency_key) "
                  "VALUES (%s, 1, %s, 'tool', %s, %s::jsonb, %s)", (rid, i, name, json.dumps({"query": "x"}), f"1:{i}:{name}"))

    async def cancel_then_chat():
        await store.cancel_run(rid)  # stop the loop after its first look at the state
        return "no tool"

    rt.script.append(cancel_then_chat)
    assert rt.drive()  # the stale lock is taken over
    assert [t[0] for t in rt.tool_calls] == ["search_nodes"]  # the read ran again; the write did not
    assert [(e[0], e[1]) for e in rt.executions(rid, kind="tool")] == [("search_nodes", "succeeded"), ("write_node", "unknown")]
    seen = rt.requests[0]["messages"][1]["content"]
    assert "OUTCOME UNKNOWN" in seen and "write_node" in seen
    assert rt.row(rid) == "cancelled" and "run.started" not in rt.types(rid)


def test_deleting_needs_the_users_confirmation(rt):
    rid, node = rt.start(), rt.node
    rt.script += [tc("delete_node", node_id=node), tc("delete_node", node_id=node),
                  tc("finish_research", outcome="inconclusive", summary="Deleted the node the user confirmed deleting.")]
    rt.drive()
    assert rt.row(rid) == "waiting_input" and rt.row(rid, "pending_input")["kind"] == "confirm_delete"
    assert rt.tool_calls == []  # the model could not authorise it
    run(store.submit_answer(rid, {"confirm": "Delete it"}))
    rt.drive()
    assert [t[0] for t in rt.tool_calls] == ["delete_node"] and rt.row(rid) == "completed"
    assert rt.row(rid, "authorized_deletes") == [node]


def test_declining_a_delete_authorises_nothing(rt):
    rid, node = rt.start(), rt.node
    rt.script += [tc("delete_node", node_id=node)]
    rt.drive()
    run(store.submit_answer(rid, {"confirm": "Keep it"}))
    assert rt.row(rid, "authorized_deletes") == [] and rt.tool_calls == []


def test_limits_give_the_model_one_chance_to_wrap_up(rt, monkeypatch):
    monkeypatch.setattr(ops, "MAX_ITERATIONS", 2)
    rid = rt.start()
    rt.script += [tc("create_plan", strategy="A plan that is long enough", tasks=[{"objective": "Investigate something"}]),
                  tc("update_task", task_id="t1", status="in_progress"),
                  tc("finish_research", outcome="inconclusive", summary="Ran out of steps before anything was investigated.")]
    rt.drive()
    assert rt.row(rid) == "completed" and rt.row(rid, "outcome") == "inconclusive"
    assert rt.pg.sql("SELECT status, reason FROM agent_tasks WHERE run_id = %s", (rid,))[0] == ("skipped", "run limit reached: the 2-step limit")
    last = rt.requests[-1]
    assert last["tool_choice"] == "required" and [t["function"]["name"] for t in last["tools"]] == ["finish_research"]
    assert "OUT OF BUDGET" in last["messages"][1]["content"]


def test_limits_without_a_wrap_up_still_end_honestly(rt, monkeypatch):
    monkeypatch.setattr(ops, "MAX_ITERATIONS", 1)
    rid = rt.start()
    rt.script += [tc("create_plan", strategy="A plan that is long enough", tasks=[{"objective": "Investigate something"}]), "I give up"]
    rt.drive()
    final = rt.row(rid, "final")
    assert rt.row(rid) == "completed" and final["outcome"] == "inconclusive" and "Stopped at the 1-step limit" in final["limitations"][0]


def test_three_invalid_steps_in_a_row_fail_the_run(rt):
    rid = rt.start()
    rt.script += ["I will think about it", tc("create_task", objective="A task without a plan"), "still thinking"]
    rt.drive()
    assert rt.row(rid) == "failed" and "3 invalid steps in a row" in rt.row(rid, "error")
    assert rt.types(rid)[-1] == "run.failed" and len(rt.executions(rid, status="failed", kind="op")) == 3


def test_one_live_run_per_project_and_cancel(rt):
    rid = rt.start()
    with pytest.raises(store.ActiveRunExists):
        rt.start()
    assert run(store.cancel_run(rid)) and not run(store.cancel_run(rid))
    assert not rt.drive() and rt.types(rid) == ["run.created", "run.cancelled"]
    assert rt.start()  # the project is free again


def test_an_unexpected_error_fails_the_run_instead_of_hanging(rt, monkeypatch):
    rid = rt.start()

    async def broken(*_a, **_k):
        raise RuntimeError("boom")

    monkeypatch.setattr(loop, "step", broken)
    rt.drive()
    assert rt.row(rid) == "failed" and "boom" in rt.row(rid, "error")


def test_a_task_with_work_done_is_unfinished_not_skipped_at_the_limit(rt, monkeypatch):
    monkeypatch.setattr(ops, "MAX_ITERATIONS", 3)
    rid = rt.start()
    rt.script += [
        tc("create_plan", strategy="A plan that is long enough", tasks=[{"objective": "Investigate the first thing"}, {"objective": "Investigate the second thing"}]),
        tc("update_task", task_id="t1", status="in_progress"),
        tc("search_nodes", query="first"),
        tc("finish_research", outcome="inconclusive", summary="Ran out of steps with the first task still being written up."),
    ]
    rt.drive()
    rows = rt.pg.sql("SELECT key, status FROM agent_tasks WHERE run_id = %s ORDER BY key", (rid,))
    assert rows == [("t1", "unfinished"), ("t2", "skipped")]
    types = rt.types(rid)
    assert types.count("run.limit") == 1 and "task.updated" in types and "task.skipped" in types
    assert types[-1] == "run.completed"


def test_alternating_bad_steps_still_fail_the_run_at_the_total_cap(rt):
    rid = rt.start()
    for _ in range(ops.MAX_INVALID_TOTAL):
        rt.script += ["thinking out loud", tc("get_research_state")]
    rt.drive()
    assert rt.row(rid) == "failed" and "rejected steps in this run" in rt.row(rid, "error")
    assert rt.row(rid, "invalid_streak") <= 1  # never three in a row: only the total cap catches this
