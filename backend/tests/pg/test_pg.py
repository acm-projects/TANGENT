import asyncio
import json
import uuid

import pytest
from sqlalchemy import text

from conftest import seed
from debate.fakes import FakeSearch, ScriptedBrain
from debate.openrouter import BrainError
from debate.pg import store
from debate.pg.adapters import PgControl, PgEmitter, PgWriter, make_context_loader
from debate.pg.checkpointer import setup_saver
from debate.pg.db import asyncpg_url, psycopg_dsn, tx
from debate.pg.worker import WorkerEnv, run_debate
from debate.schemas import AskAction, Question, Usage

U = Usage(model="fake/model", prompt_tokens=100, completion_tokens=20, cost=0.01, latency_ms=5)


def run(coro):
    return asyncio.run(coro)


def new_debate(pg, ids, **kw):
    async def go():
        async with tx(pg.factory, user_id=ids["user"]) as s:
            return await store.create_debate(
                s, owner_id=ids["user"], project_id=ids["project"], parent_node_id=ids["nodes"][-1], topic="alpha vs beta",
                for_model="m/for", against_model="m/against", judge_model="m/judge", **kw,
            )

    return run(go())


def env_for(pg, brain=None, **kw):
    run(setup_saver(pg.app_url))
    return WorkerEnv(
        factory=pg.factory, database_url=pg.app_url, make_brain=lambda row: brain or ScriptedBrain(usage=U),
        search=FakeSearch(), heartbeat_s=30, **kw,
    )


def status(pg, did):
    return pg.sql("SELECT status::text, end_reason::text, result_node_id IS NOT NULL FROM debates WHERE id=%s", (did,))[0]


def count(pg, q, *a):
    return pg.sql(q, a)[0][0]


# ---------- pure helpers ----------

def test_url_helpers_translate_between_drivers():
    assert asyncpg_url("postgresql://u:p@h:5432/d?sslmode=require") == "postgresql+asyncpg://u:p@h:5432/d?ssl=require"
    assert asyncpg_url("postgresql+asyncpg://u:p@h/d?ssl=require").endswith("?ssl=require")
    dsn = psycopg_dsn("postgresql+asyncpg://u:p@h/d?ssl=require")
    assert dsn.startswith("postgresql://") and "sslmode=require" in dsn and "options=-c%20search_path%3Dlanggraph" in dsn


# ---------- the DDL and row level security ----------

def test_owner_sees_own_debates_and_nobody_else_does(pg):
    a, b = seed(pg), seed(pg)
    did = new_debate(pg, a)

    async def go():
        async with tx(pg.factory, user_id=b["user"]) as s:
            assert await store.get_debate(s, did) is None
            assert await store.read_events(s, did) == []
            with pytest.raises(store.StateError):
                await store.request_control(s, did, "stop")
        async with tx(pg.factory, user_id=a["user"]) as s:
            assert (await store.get_debate(s, did))["status"] == "queued"

    run(go())


def test_a_user_cannot_start_a_debate_in_someone_elses_project(pg):
    a, b = seed(pg), seed(pg)

    async def go():
        async with tx(pg.factory, user_id=b["user"]) as s:
            await store.create_debate(
                s, owner_id=b["user"], project_id=a["project"], parent_node_id=a["nodes"][0], topic="t",
                for_model="x", against_model="y", judge_model="z",
            )

    with pytest.raises(Exception, match="row-level security"):
        run(go())


def test_no_identity_means_no_rows(pg):
    a = seed(pg)
    new_debate(pg, a)

    async def go():
        async with tx(pg.factory) as s:
            return (await s.execute(text("SELECT count(*) FROM debates"))).scalar_one()

    assert run(go()) == 0


def test_create_debate_validates_rounds_and_allows_same_model(pg):
    a = seed(pg)
    with pytest.raises(store.StateError):
        new_debate(pg, a, rounds=4)

    async def same():
        async with tx(pg.factory, user_id=a["user"]) as s:
            await store.create_debate(s, owner_id=a["user"], project_id=a["project"], parent_node_id=a["nodes"][0],
                                      topic="t", for_model="x", against_model="x", judge_model="j")

    run(same())  # one model on both sides is the default


# ---------- adapters ----------

def test_emitter_is_idempotent_validates_types_and_tracks_phase(pg):
    a = seed(pg)
    did = new_debate(pg, a)
    em = PgEmitter(pg.factory, a["user"], did)

    async def go():
        assert await em.emit("thinking", {"text": "x"}, key="k1") is True
        assert await em.emit("thinking", {"text": "x"}, key="k1") is False
        assert await em.emit("thinking", {"text": "y"}) is True and await em.emit("thinking", {"text": "y"}) is True
        await em.emit("phase_changed", {"phase": "rebuttal", "round": 2}, key="p1")
        await em.emit("phase_changed", {"phase": "done", "round": 2}, key="p2")
        with pytest.raises(ValueError):
            await em.emit("nonsense", {})

    run(go())
    assert count(pg, "SELECT count(*) FROM debate_events WHERE debate_id=%s", did) == 5
    assert pg.sql("SELECT current_phase::text, current_round FROM debates WHERE id=%s", (did,))[0] == ("judging", 2)


def test_control_requests_are_seen_once_applied(pg):
    a = seed(pg)
    did = new_debate(pg, a)
    ctl = PgControl(pg.factory, a["user"])

    async def go():
        assert await ctl.pending(did) is None
        async with tx(pg.factory, user_id=a["user"]) as s:
            await s.execute(text("UPDATE debates SET status='running' WHERE id=CAST(:d AS uuid)"), {"d": did})
            r = await store.request_control(s, did, "pick_side", "against")
        c = await ctl.pending(did)
        assert c.action == "pick_side" and c.side == "against" and c.id == r["control"]["id"]
        assert await ctl.pending(did, applied_id=c.id) is None
        async with tx(pg.factory, user_id=a["user"]) as s:
            with pytest.raises(store.StateError):
                await store.request_control(s, did, "pick_side", "sideways")
            with pytest.raises(store.StateError):
                await store.request_control(s, did, "explode")

    run(go())


def test_context_loader_follows_the_parent_chain_only(pg):
    a = seed(pg, 3)
    other = seed(pg, 1)
    sibling = pg.sql(
        "INSERT INTO nodes (tree_id, project_id, parent_id, created_by_id, chats, fork_index) VALUES (%s,%s,%s,%s,%s::jsonb,%s) RETURNING id",
        (a["tree"], a["project"], a["nodes"][0], a["user"], '[{"role":"user","content":"sibling idea"}]', 7),
    )[0][0]
    pg.sql("INSERT INTO node_merge_sources (node_id, source_leaf_id) VALUES (%s,%s)", (a["nodes"][2], sibling))
    did = new_debate(pg, a)
    text_, ids = run(make_context_loader(pg.factory, a["user"])(did))
    assert ids == a["nodes"]
    assert text_.index("question 0") < text_.index("question 2")
    assert "sibling idea" not in text_  # a merge node carries its branches inside its own chats
    assert other["nodes"][0] not in ids


def test_context_is_empty_for_a_node_the_owner_cannot_see(pg):
    a, b = seed(pg, 2), seed(pg, 2)
    did = new_debate(pg, a)
    text_, ids = run(make_context_loader(pg.factory, b["user"])(did))
    assert text_ == "" and ids == []


def test_writer_creates_one_node_once_and_records_timing(pg):
    a = seed(pg)
    did = new_debate(pg, a)
    payload = {
        "proposition": "P", "winner": "for", "judge_would_have_chosen": "for", "confidence": 0.734, "summary": "sum",
        "final_output": "final", "rationale": "why", "scores": {"for": 8, "against": 5},
        "strongest_counterpoints": ["c"], "verdict_flips_if": ["v"], "citations": [{"id": "e1"}], "clarifications": [],
        "end_reason": "rounds_exhausted", "timings": [{"node": "agent", "duration_ms": 5}], "timing_summary": {"phases": {}},
        "usage": [{"cost": 0.02}], "usage_summary": {"total": {"cost": 0.02}},
    }
    w = PgWriter(pg.factory, a["user"])
    n1, n2 = run(w.create_result(did, payload)), run(w.create_result(did, payload))
    assert n1 == n2
    assert count(pg, "SELECT count(*) FROM nodes WHERE node_type='debate'") == 1
    assert count(pg, "SELECT count(*) FROM debate_results") == 1
    node = pg.sql("SELECT parent_id::text, project_id::text, node_type::text, fork_index, chats FROM nodes WHERE id=%s", (n1,))[0]
    assert node[:3] == (a["nodes"][-1], a["project"], "debate") and node[3] == 1
    assert [m["role"] for m in node[4]] == ["user", "assistant"]
    assert [m["seq"] for m in node[4]] == [0, 1] and all(m["branch_source"] is None and m["created_at"] for m in node[4])
    t = pg.sql("SELECT title, summary, status FROM nodes WHERE id=%s", (n1,))[0]
    assert t[0].startswith("FOR wins: ") and t[1:] == ("sum", "active")
    assert "**Verdict: FOR**" in node[4][1]["content"] and "final" in node[4][1]["content"]
    r = pg.sql("SELECT winner::text, confidence, cost_usd, wall_ms, active_ms, waited_ms, scores FROM debate_results")[0]
    assert r[0] == "for" and float(r[1]) == 0.73 and float(r[2]) == 0.02 and r[3] >= r[4] >= 0 and r[5] == max(0, r[3] - r[4])
    assert r[6] == {"for": 8, "against": 5}
    d = pg.sql("SELECT status::text, result_node_id::text, completed_at IS NOT NULL, lease_until FROM debates WHERE id=%s", (did,))[0]
    assert d == ("completed", n1, True, None)


def test_writer_refuses_to_write_for_someone_else(pg):
    a, b = seed(pg), seed(pg)
    did = new_debate(pg, a)
    with pytest.raises(LookupError):
        run(PgWriter(pg.factory, b["user"]).create_result(did, {}))
    assert count(pg, "SELECT count(*) FROM nodes WHERE node_type='debate'") == 0


# ---------- the worker, end to end on real Postgres and the real LangGraph Postgres checkpointer ----------

def checkpoints(pg, did):
    return count(pg, "SELECT count(*) FROM langgraph.checkpoints WHERE thread_id=%s", did)


def test_full_debate_completes_stores_the_result_and_purges_everything_transient(pg):
    a = seed(pg)
    did = new_debate(pg, a)
    e = env_for(pg)
    assert run(run_debate(e, did)) == "done"
    assert status(pg, did) == ("completed", "rounds_exhausted", True)
    assert checkpoints(pg, did) == 0
    assert count(pg, "SELECT count(*) FROM debate_events WHERE debate_id=%s", did) > 5
    assert run(store.purge_finished_events(pg.factory, older_than_s=3600)) == 0
    assert run(store.purge_finished_events(pg.factory, older_than_s=0)) > 5
    assert count(pg, "SELECT count(*) FROM debate_events WHERE debate_id=%s", did) == 0
    r = pg.sql("SELECT cost_usd, usage_summary->'total'->>'calls', jsonb_array_length(timings), jsonb_array_length(usage) FROM debate_results")[0]
    assert float(r[0]) > 0 and int(r[1]) == r[3] and r[2] > 10
    d = pg.sql("SELECT jsonb_array_length(segments), active_ms, wall_ms, waited_ms, current_phase FROM debates WHERE id=%s", (did,))[0]
    assert d[0] == 1 and d[1] >= 0 and d[2] >= d[1] and d[4] is None
    assert run(run_debate(e, did)) == "noop"
    assert count(pg, "SELECT count(*) FROM nodes WHERE node_type='debate'") == 1


def test_question_pauses_the_debate_and_the_answer_resumes_it(pg):
    a = seed(pg)
    did = new_debate(pg, a)
    q = Question(prompt="What is your budget?", options=[{"label": "low"}, {"label": "high"}])
    brain = ScriptedBrain({("for", "rebuttal", 1, 0): AskAction(questions=[q], thinking="need budget")}, usage=U)
    e = env_for(pg, brain)

    assert run(run_debate(e, did)) == "paused"
    st = pg.sql("SELECT status::text, pending_questions, lease_until, jsonb_array_length(segments) FROM debates WHERE id=%s", (did,))[0]
    assert st[0] == "awaiting_input" and st[1][0]["prompt"] == "What is your budget?" and st[1][0]["asked_by"] == ["for"] and st[2] is None
    assert checkpoints(pg, did) > 0
    assert count(pg, "SELECT count(*) FROM debate_events WHERE event_type='question_requested'") == 1

    async def answer():
        async with tx(pg.factory, user_id=a["user"]) as s:
            with pytest.raises(store.StateError):
                await store.submit_answer(s, did, {"bogus": "x"})
            return await store.submit_answer(s, did, {q.id: "high"})

    payload = run(answer())
    assert status(pg, did)[0] == "queued"
    assert pg.sql("SELECT resume_payload FROM debates WHERE id=%s", (did,))[0][0] == {"answers": {q.id: "high"}, "skip": False}
    assert run(run_debate(e, did)) == "done"
    assert pg.sql("SELECT resume_payload FROM debates WHERE id=%s", (did,))[0][0] is None
    assert status(pg, did) == ("completed", "rounds_exhausted", True)
    clar = pg.sql("SELECT clarifications FROM debate_results")[0][0]
    assert clar[0]["answer"] == "high" and clar[0]["asked_by"] == "for"
    d = pg.sql("SELECT jsonb_array_length(segments), waited_ms >= 0 FROM debates WHERE id=%s", (did,))[0]
    assert d[0] == 2


def test_user_can_pick_a_side_while_the_debate_waits_on_a_question(pg):
    a = seed(pg)
    did = new_debate(pg, a)
    q = Question(prompt="Budget?")
    e = env_for(pg, ScriptedBrain({("for", "rebuttal", 1, 0): AskAction(questions=[q], thinking="t")}, usage=U))
    assert run(run_debate(e, did)) == "paused"

    async def pick():
        async with tx(pg.factory, user_id=a["user"]) as s:
            return await store.request_control(s, did, "pick_side", "against")

    r = run(pick())
    assert r["needs_resume"] and status(pg, did)[0] == "queued"
    assert run(run_debate(e, did)) == "done"
    assert status(pg, did)[1] == "user_picked"
    assert pg.sql("SELECT winner::text, judge_would_have_chosen::text FROM debate_results")[0][0] == "against"


def test_time_slicing_over_many_invocations_produces_the_same_single_node(pg):
    a = seed(pg)
    did = new_debate(pg, a)
    e = env_for(pg)
    outcomes = []
    for _ in range(300):
        o = run(run_debate(e, did, time_left_ms=lambda: 0))
        outcomes.append(o)
        if o == "done":
            break
        assert o == "continue" and status(pg, did)[0] == "queued"
    assert outcomes[-1] == "done" and len(outcomes) > 5
    assert status(pg, did) == ("completed", "rounds_exhausted", True)
    assert count(pg, "SELECT count(*) FROM nodes WHERE node_type='debate'") == 1
    assert count(pg, "SELECT jsonb_array_length(segments) FROM debates WHERE id=%s", did) == len(outcomes)
    plain = new_debate(pg, a)
    assert run(run_debate(e, plain)) == "done"
    calls = lambda d: count(pg, "SELECT jsonb_array_length(usage) FROM debate_results WHERE debate_id=%s", d)
    assert calls(did) == calls(plain)


def test_a_second_worker_cannot_run_a_debate_that_is_already_leased(pg):
    a = seed(pg)
    did = new_debate(pg, a)
    e = env_for(pg)
    assert run(store.acquire_lease(pg.factory, did, 60)) is True
    assert run(run_debate(e, did)) == "busy"
    pg.sql("UPDATE debates SET lease_until = now() - interval '1 second' WHERE id=%s", (did,))
    assert run(run_debate(e, did)) == "done"


def test_retain_artifacts_keeps_events_and_checkpoints_for_debugging(pg):
    a = seed(pg)
    did = new_debate(pg, a, retain_artifacts=True)
    assert run(run_debate(env_for(pg), did)) == "done"
    run(store.purge_finished_events(pg.factory, older_than_s=0))
    assert count(pg, "SELECT count(*) FROM debate_events WHERE debate_id=%s", did) > 5
    assert checkpoints(pg, did) > 0


def test_model_failures_mark_the_debate_failed_with_a_code(pg):
    a = seed(pg)
    did = new_debate(pg, a)

    class Broken(ScriptedBrain):
        async def step(self, ctx, sink=None):  # sink is passed whenever token streaming is on
            raise BrainError("openrouter_credits", "out of credits")

    assert run(run_debate(env_for(pg, Broken()), did)) == "failed"
    assert pg.sql("SELECT status::text, error_code, lease_until FROM debates WHERE id=%s", (did,))[0] == ("failed", "openrouter_credits", None)
    assert count(pg, "SELECT count(*) FROM debate_events WHERE event_type='failed' AND debate_id=%s", did) == 1
    assert checkpoints(pg, did) == 0


def test_unexpected_errors_are_retried_then_failed(pg):
    a = seed(pg)
    did = new_debate(pg, a)

    class Flaky(ScriptedBrain):
        async def frame(self, topic, context):
            raise RuntimeError("boom")

    e = env_for(pg, Flaky(), max_attempts=2)
    with pytest.raises(RuntimeError):
        run(run_debate(e, did, attempt=1))
    assert status(pg, did)[0] == "queued"
    assert run(run_debate(e, did, attempt=2)) == "failed"
    assert pg.sql("SELECT error_code FROM debates WHERE id=%s", (did,))[0][0] == "internal_error"


def test_cancelling_stops_a_running_debate_and_a_cancelled_one_never_restarts(pg):
    a = seed(pg)
    did = new_debate(pg, a)

    class Slow(ScriptedBrain):
        async def step(self, ctx, sink=None):  # sink arrives when token streaming is on
            async with tx(pg.factory, user_id=a["user"]) as s:
                await store.cancel_debate(s, did)
            await asyncio.sleep(0.5)
            return await super().step(ctx)

    e = env_for(pg, Slow(usage=U))
    e.heartbeat_s = 0.05
    assert run(run_debate(e, did)) == "stopped"
    assert status(pg, did)[0] == "cancelled" and count(pg, "SELECT count(*) FROM nodes WHERE node_type='debate'") == 0
    assert run(run_debate(e, did)) == "noop"


def test_cancel_only_works_on_active_debates(pg):
    a = seed(pg)
    did = new_debate(pg, a)

    async def go():
        async with tx(pg.factory, user_id=a["user"]) as s:
            assert await store.cancel_debate(s, did) is True
            assert await store.cancel_debate(s, did) is False

    run(go())


def test_state_transitions_are_refused_when_the_debate_is_not_in_the_right_state(pg):
    a = seed(pg)
    did = new_debate(pg, a)

    async def go():
        async with tx(pg.factory, user_id=a["user"]) as s:
            with pytest.raises(store.StateError):
                await store.submit_answer(s, did, {}, skip=True)
            await store.cancel_debate(s, did)
            with pytest.raises(store.StateError):
                await store.request_control(s, did, "stop")
            with pytest.raises(store.StateError):
                await store.submit_answer(s, did, {})

    run(go())


def test_sweeper_queries_find_only_debates_that_are_really_stuck(pg):
    a = seed(pg)
    fresh, stale_queued, dead_runner, paused, healthy = (new_debate(pg, a) for _ in range(5))
    pg.sql("UPDATE debates SET updated_at = now() - interval '10 minutes' WHERE id=%s", (stale_queued,))
    pg.sql("UPDATE debates SET status='running', lease_until = now() - interval '1 minute' WHERE id=%s", (dead_runner,))
    pg.sql("UPDATE debates SET status='awaiting_input', updated_at = now() - interval '1 day' WHERE id=%s", (paused,))
    pg.sql("UPDATE debates SET status='running', lease_until = now() + interval '1 minute' WHERE id=%s", (healthy,))
    found = set(run(store.find_stuck(pg.factory)))
    assert found == {str(stale_queued), str(dead_runner)}


def test_overdue_debates_are_failed_as_expired(pg):
    a = seed(pg)
    old, new = new_debate(pg, a), new_debate(pg, a)
    pg.sql("UPDATE debates SET expires_at = now() - interval '1 second', status='awaiting_input' WHERE id=%s", (old,))
    assert run(store.expire_overdue(pg.factory)) == [str(old)]
    assert pg.sql("SELECT status::text, error_code FROM debates WHERE id=%s", (old,))[0] == ("failed", "expired")
    assert status(pg, new)[0] == "queued"


def test_terminal_debates_listed_for_checkpoint_cleanup_exclude_retained_ones(pg):
    a = seed(pg)
    cancelled, retained, active = new_debate(pg, a), new_debate(pg, a, retain_artifacts=True), new_debate(pg, a)

    async def go():
        async with tx(pg.factory, user_id=a["user"]) as s:
            await store.cancel_debate(s, cancelled)
            await store.cancel_debate(s, retained)

    run(go())
    assert run(store.finished_without_cleanup(pg.factory)) == [str(cancelled)]


def test_writer_takes_the_next_free_fork_index_and_survives_a_taken_slot(pg):
    a = seed(pg)
    parent = a["nodes"][-1]
    for idx in (1, 2):
        pg.sql(
            "INSERT INTO nodes (tree_id, project_id, parent_id, created_by_id, fork_index) VALUES (%s,%s,%s,%s,%s)",
            (a["tree"], a["project"], parent, a["user"], idx),
        )
    did = new_debate(pg, a)
    payload = {"proposition": "P", "winner": "against", "confidence": 0.5, "summary": "s", "final_output": "f",
               "rationale": "r", "end_reason": "rounds_exhausted"}
    n = run(PgWriter(pg.factory, a["user"]).create_result(did, payload))
    assert pg.sql("SELECT fork_index FROM nodes WHERE id=%s", (n,))[0][0] == 3


def test_writer_titles_and_chats_for_picked_and_stopped(pg):
    a = seed(pg)
    for reason, win, would, title, phrase in [
        ("user_picked", "against", "for", "AGAINST (your pick): ", "would have picked FOR"),
        ("user_stopped", "no_clear_winner", "no_clear_winner", "Stopped early: ", "ended the debate early"),
    ]:
        did = new_debate(pg, a)
        payload = {"proposition": "P", "winner": win, "judge_would_have_chosen": would, "confidence": 0.5, "summary": "s",
                   "final_output": "f", "rationale": "r", "end_reason": reason}
        n = run(PgWriter(pg.factory, a["user"]).create_result(did, payload))
        t, chats = pg.sql("SELECT title, chats FROM nodes WHERE id=%s", (n,))[0]
        assert t.startswith(title) and phrase in chats[1]["content"]


def test_by_node_endpoint_data(pg):
    a, b = seed(pg), seed(pg)
    did = new_debate(pg, a)
    payload = {"proposition": "P", "winner": "for", "judge_would_have_chosen": "for", "confidence": 0.7, "summary": "s",
               "final_output": "f", "rationale": "r", "scores": {}, "end_reason": "rounds_exhausted"}
    n = run(PgWriter(pg.factory, a["user"]).create_result(did, payload))

    async def get(u):
        async with tx(pg.factory, user_id=u) as s:
            return await store.get_result_by_node(s, n)

    assert run(get(a["user"]))["winner"] == "for" and run(get(b["user"])) is None
