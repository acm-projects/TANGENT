import asyncio
import json
import uuid

import httpx
import pytest
from fastapi import FastAPI, Header, HTTPException

from conftest import seed
from test_pg import new_debate
from debate.fakes import FakeSearch, ScriptedBrain
from debate.pg import store
from debate.pg.api import DebateSettings, JudgeOption, ModelOption, build_router, family, pick_judge
from debate.pg.checkpointer import setup_saver
from debate.pg.db import tx
from debate.pg.handler import handle, sweep
from debate.pg.worker import WorkerEnv, run_debate
from debate.schemas import AskAction, Branch, Question, Usage

MODELS = [ModelOption("anthropic/claude-x", "Claude"), ModelOption("openai/gpt-x", "GPT"), ModelOption("google/gemini-x", "Gemini")]
JUDGES = [JudgeOption("google/gemini-judge", "google"), JudgeOption("anthropic/claude-judge", "anthropic")]
U = Usage(model="fake", prompt_tokens=10, completion_tokens=5, cost=0.001)


def run(coro):
    return asyncio.run(coro)


class Queue:
    def __init__(self):
        self.ids = asyncio.Queue()
        self.sent = []

    async def enqueue(self, debate_id):
        self.sent.append(debate_id)
        await self.ids.put(debate_id)


async def current_user(x_user: str = Header(default="")):
    if not x_user:
        raise HTTPException(401, "no user")
    return x_user


def app_for(pg, q, **kw):
    settings = DebateSettings(allowed_models=MODELS, judges=JUDGES, sse_poll_s=kw.pop('poll', 0.02), sse_heartbeat_s=0.1, **kw)
    app = FastAPI()
    app.include_router(build_router(factory=pg.factory, current_user=current_user, enqueue=q, settings=settings))
    return app


def client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


def body(ids, **over):
    b = {"project_id": ids["project"], "node_id": ids["nodes"][-1], "topic": "alpha vs beta",
         "models": ["anthropic/claude-x"]}
    b.update(over)
    return b


def H(u):
    return {"x-user": u}


def test_judge_is_always_from_a_family_that_is_not_debating():
    assert family("Google/Gemini-2") == "google"
    assert pick_judge("anthropic/a", "openai/b", JUDGES) == "google/gemini-judge"
    assert pick_judge("google/a", "openai/b", JUDGES) == "anthropic/claude-judge"
    with pytest.raises(ValueError):
        pick_judge("google/a", "anthropic/b", JUDGES)


def test_start_validates_models_rounds_ownership_and_limits(pg):
    a, b = seed(pg), seed(pg)
    q = Queue()

    async def go():
        async with client(app_for(pg, q)) as c:
            r = await c.get("/debates/models", headers=H(a["user"]))
            assert [m["id"] for m in r.json()["models"]] == [m.id for m in MODELS] and r.json()["default"] == MODELS[0].id
            assert (await c.post("/debates", json=body(a), headers={})).status_code == 401
            assert (await c.post("/debates", json=body(a, models=["evil/model"]), headers=H(a["user"]))).status_code == 422
            assert (await c.post("/debates", json=body(a, models=["anthropic/claude-x", "evil/model"]), headers=H(a["user"]))).status_code == 422
            assert (await c.post("/debates", json=body(a, models=[]), headers=H(a["user"]))).status_code == 422
            assert (await c.post("/debates", json=body(a, models=["anthropic/claude-x", "openai/gpt-x", "anthropic/claude-x"]), headers=H(a["user"]))).status_code == 422
            assert (await c.post("/debates", json=body(a, rounds=4), headers=H(a["user"]))).status_code == 422
            assert (await c.post("/debates", json=body(a, topic="x"), headers=H(a["user"]))).status_code == 422
            assert (await c.post("/debates", json=body(a), headers=H(b["user"]))).status_code == 404
            assert q.sent == []
            r = await c.post("/debates", json=body(a), headers=H(a["user"]))
            assert r.status_code == 202 and q.sent == [r.json()["id"]]
            d = (await c.get(f"/debates/{r.json()['id']}", headers=H(a["user"]))).json()
            assert d["status"] == "queued" and d["for_model"] == d["against_model"] == "anthropic/claude-x" and r.json()["model_mode"] == "same"
            assert (await c.get(f"/debates/{r.json()['id']}", headers=H(b["user"]))).status_code == 404
            assert (await c.post("/debates", json=body(a), headers=H(a["user"]))).status_code == 202
            assert (await c.post("/debates", json=body(a), headers=H(a["user"]))).status_code == 429

    run(go())
    assert pg.sql("SELECT judge_model, retain_artifacts FROM debates LIMIT 1")[0] == ("google/gemini-judge", False)


def test_retain_artifacts_is_only_honoured_in_dev(pg):
    a = seed(pg)
    q = Queue()

    async def go(dev):
        async with client(app_for(pg, q, dev=dev)) as c:
            return (await c.post("/debates", json=body(a, retain_artifacts=True), headers=H(a["user"]))).json()["id"]

    prod, dev = run(go(False)), run(go(True))
    assert pg.sql("SELECT retain_artifacts FROM debates WHERE id=%s", (prod,))[0][0] is False
    assert pg.sql("SELECT retain_artifacts FROM debates WHERE id=%s", (dev,))[0][0] is True


def test_enqueue_failure_leaves_a_queued_row_for_the_sweeper(pg):
    a = seed(pg)

    class Broken:
        async def enqueue(self, debate_id):
            raise RuntimeError("sqs down")

    async def go():
        async with client(app_for(pg, Broken())) as c:
            return await c.post("/debates", json=body(a), headers=H(a["user"]))

    assert run(go()).status_code == 503
    did = pg.sql("SELECT id::text FROM debates")[0][0]
    pg.sql("UPDATE debates SET updated_at = now() - interval '5 minutes' WHERE id=%s", (did,))
    q = Queue()
    env = WorkerEnv(factory=pg.factory, database_url=pg.app_url, make_brain=lambda r: None, search=None)
    assert run(sweep(env, q))["requeued"] == [did] and q.sent == [did]


def worker_env(pg, brain, **kw):
    run(setup_saver(pg.app_url))
    return WorkerEnv(factory=pg.factory, database_url=pg.app_url, make_brain=lambda r: brain, search=FakeSearch(), heartbeat_s=30, **kw)


def test_whole_flow_api_queue_worker_sse_answer_and_replay(pg):
    a, b = seed(pg), seed(pg)
    question = Question(prompt="What is your budget?", options=[{"label": "low"}, {"label": "high"}])
    brain = ScriptedBrain({("for", "rebuttal", 1, 0): AskAction(questions=[question], thinking="need the budget")}, usage=U)
    env = worker_env(pg, brain)
    q = Queue()

    async def consumer():
        while True:
            did = await q.ids.get()
            await run_debate(env, did)

    async def user(c, did):
        for _ in range(500):
            d = (await c.get(f"/debates/{did}", headers=H(a["user"]))).json()
            if d["status"] == "awaiting_input":
                qid = d["pending_questions"][0]["id"]
                assert (await c.post(f"/debates/{did}/answer", json={"answers": {"bogus": 1}}, headers=H(a["user"]))).status_code == 409
                r = await c.post(f"/debates/{did}/answer", json={"answers": {qid: "high"}}, headers=H(a["user"]))
                assert r.status_code == 202
                return
            await asyncio.sleep(0.02)
        raise AssertionError("never asked")

    async def stream(c, did, user_id, headers=None):
        out = []
        async with c.stream("GET", f"/debates/{did}/events", headers={**H(user_id), **(headers or {})}) as r:
            assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
            ev, eid = None, None
            async for line in r.aiter_lines():
                if line.startswith("id: "):
                    eid = int(line[4:])
                elif line.startswith("event: "):
                    ev = line[7:]
                elif line.startswith("data: "):
                    out.append((ev, eid, json.loads(line[6:])))
                    ev, eid = None, None
        return out

    async def go():
        async with client(app_for(pg, q)) as c:
            did = (await c.post("/debates", json=body(a), headers=H(a["user"]))).json()["id"]
            worker = asyncio.create_task(consumer())
            try:
                other = await c.get(f"/debates/{did}/events", headers=H(b["user"]))
                assert other.status_code == 404
                events, _ = await asyncio.wait_for(asyncio.gather(stream(c, did, a["user"]), user(c, did)), 60)
                replay = await stream(c, did, a["user"], {"last-event-id": str(next(i for _, i, _ in events if i))})
            finally:
                worker.cancel()
            return did, events, replay

    did, events, replay = run(go())
    kinds = [k for k, _, _ in events]
    assert kinds[0] == "state" and kinds[-1] == "done"
    assert "thinking" in kinds and "turn_completed" in kinds
    assert kinds.index("question_requested") < kinds.index("answer_received") < kinds.index("completed")
    ids = [i for _, i, _ in events if i]
    assert ids == sorted(ids) and len(ids) == len(set(ids))
    done = events[-1][2]
    assert done["status"] == "completed" and done["result_node_id"]
    assert pg.sql("SELECT chats->1->>'role' FROM nodes WHERE node_type='debate'")[0][0] == "assistant"
    assert len(replay) < len(events) and all(i is None or i > ids[0] for _, i, _ in replay)
    assert replay[-1][0] == "done"


def test_stream_ends_with_done_even_after_the_events_are_purged(pg):
    a = seed(pg)
    q = Queue()
    env = worker_env(pg, ScriptedBrain(usage=U))

    async def go():
        async with client(app_for(pg, q)) as c:
            did = (await c.post("/debates", json=body(a), headers=H(a["user"]))).json()["id"]
            assert await run_debate(env, did) == "done"
            await store.purge_finished_events(pg.factory, older_than_s=0)
            r = await c.get(f"/debates/{did}/events", headers=H(a["user"]))
            return r.text

    text = run(go())
    assert "event: state" in text and "event: done" in text and "event: thinking" not in text


def test_control_while_waiting_requeues_and_cancel_is_final(pg):
    a = seed(pg)
    q = Queue()
    brain = ScriptedBrain({("for", "rebuttal", 1, 0): AskAction(questions=[Question(prompt="Budget?")], thinking="t")}, usage=U)
    env = worker_env(pg, brain)

    async def flow():
        async with client(app_for(pg, q)) as c:
            did = (await c.post("/debates", json=body(a), headers=H(a["user"]))).json()["id"]
            assert await run_debate(env, did) == "paused"
            before = len(q.sent)
            assert (await c.post(f"/debates/{did}/control", json={"action": "pick_side"}, headers=H(a["user"]))).status_code == 409
            assert len(q.sent) == before
            r = await c.post(f"/debates/{did}/control", json={"action": "pick_side", "side": "against"}, headers=H(a["user"]))
            assert r.json()["resumed"] is True and len(q.sent) == before + 1
            assert await run_debate(env, did) == "done"
            assert (await c.get(f"/debates/{did}", headers=H(a["user"]))).json()["end_reason"] == "user_picked"
            assert (await c.post(f"/debates/{did}/cancel", headers=H(a["user"]))).status_code == 409
            did2 = (await c.post("/debates", json=body(a), headers=H(a["user"]))).json()["id"]
            assert (await c.post(f"/debates/{did2}/cancel", headers=H(a["user"]))).status_code == 202
            assert (await c.get(f"/debates/{did2}", headers=H(a["user"]))).json()["status"] == "cancelled"

    run(flow())


class Ctx:
    def __init__(self, ms=10**9):
        self.ms = ms

    def get_remaining_time_in_millis(self):
        return self.ms


def record(did, mid="m1", count=1):
    return {"Records": [{"messageId": mid, "body": json.dumps({"debate_id": did}), "attributes": {"ApproximateReceiveCount": str(count)}}]}


def test_lambda_handler_runs_requeues_and_reports_failures(pg):
    a = seed(pg)
    q = Queue()
    env = worker_env(pg, ScriptedBrain(usage=U))
    env.min_slice_ms = 20_000
    did = new = None

    async def go():
        nonlocal did
        async with client(app_for(pg, q)) as c:
            did = (await c.post("/debates", json=body(a), headers=H(a["user"]))).json()["id"]
        out = await handle(record(did), Ctx(0), env, q)
        assert out == {"batchItemFailures": []}
        assert len(q.sent) == 2 and q.sent[1] == did
        n = 0
        while pg.sql("SELECT status::text FROM debates WHERE id=%s", (did,))[0][0] != "completed" and n < 300:
            await handle(record(did), Ctx(0), env, q)
            n += 1
        assert pg.sql("SELECT status::text FROM debates WHERE id=%s", (did,))[0][0] == "completed"
        assert await handle(record(did, "m2"), Ctx(), env, q) == {"batchItemFailures": []}
        assert await store.acquire_lease(pg.factory, did, 60) is False
        bad = {"Records": [{"messageId": "m3", "body": "not json", "attributes": {}}]}
        assert await handle(bad, Ctx(), env, q) == {"batchItemFailures": [{"itemIdentifier": "m3"}]}

    run(go())
    assert pg.sql("SELECT count(*) FROM nodes WHERE node_type='debate'")[0][0] == 1


def test_busy_debates_are_returned_to_the_queue(pg):
    a = seed(pg)
    q = Queue()
    env = worker_env(pg, ScriptedBrain(usage=U))

    async def go():
        async with client(app_for(pg, q)) as c:
            did = (await c.post("/debates", json=body(a), headers=H(a["user"]))).json()["id"]
        assert await store.acquire_lease(pg.factory, did, 60)
        return await handle(record(did, "m9"), Ctx(), env, q)

    assert run(go()) == {"batchItemFailures": [{"itemIdentifier": "m9"}]}


def test_sqs_enqueuer_sends_only_the_id_in_a_per_debate_group():
    from debate.pg.queue import SqsEnqueuer

    class Fake:
        calls = []

        def send_message(self, **kw):
            self.calls.append(kw)

    f = Fake()
    run(SqsEnqueuer("https://sqs/q.fifo", f).enqueue("abc"))
    run(SqsEnqueuer("https://sqs/q.fifo", f).enqueue("abc"))
    c = f.calls
    assert json.loads(c[0]["MessageBody"]) == {"debate_id": "abc"} and c[0]["MessageGroupId"] == "abc"
    assert c[0]["MessageDeduplicationId"] != c[1]["MessageDeduplicationId"]


def test_stream_waits_one_beat_for_the_event_written_just_after_the_status_flips(pg):
    a = seed(pg)
    q = Queue()

    async def go():
        async with client(app_for(pg, q, poll=0.2)) as c:
            did = (await c.post("/debates", json=body(a), headers=H(a["user"]))).json()["id"]
            pg.sql("UPDATE debates SET status='completed', completed_at=now() WHERE id=%s", (did,))

            async def late():
                await asyncio.sleep(0.06)
                pg.sql("INSERT INTO debate_events (debate_id, event_type, payload) VALUES (%s, 'completed', '{}')", (did,))

            t = asyncio.create_task(late())
            r = await c.get(f"/debates/{did}/events", headers=H(a["user"]))
            await t
            return r.text

    text = run(go())
    assert text.index("event: completed") < text.index("event: done")


def test_inline_enqueuer_runs_a_debate_with_no_queue(pg):
    from debate.pg.local import InlineEnqueuer

    ids = seed(pg)
    run(setup_saver(pg.app_url))
    env = WorkerEnv(factory=pg.factory, database_url=pg.app_url, make_brain=lambda row: ScriptedBrain(usage=U),
                    search=FakeSearch(), min_slice_ms=0)
    q = InlineEnqueuer(env)

    async def go():
        async with client(app_for(pg, q)) as c:
            r = await c.post("/debates", json=body(ids), headers={"x-user": ids["user"]})
            assert r.status_code == 202, r.text
            await q.drain()
            return r.json()["id"]

    did = run(go())
    assert pg.sql("SELECT status::text FROM debates WHERE id=%s", (did,))[0][0] == "completed"
    assert pg.sql("SELECT count(*) FROM nodes WHERE node_type='debate'")[0][0] == 1


def test_sse_over_a_real_socket_delivers_events_while_the_debate_runs(pg):
    """Real uvicorn + real TCP: events must arrive spread over time (not buffered to the end), framed like the chat SSE."""
    import threading
    import time

    import httpx
    import uvicorn

    from debate.pg.local import InlineEnqueuer

    class Slow(ScriptedBrain):
        async def frame(self, *a, **k):
            await asyncio.sleep(0.4)
            return await super().frame(*a, **k)

        async def step(self, *a, **k):
            await asyncio.sleep(0.25)
            return await super().step(*a, **k)

        async def judge(self, *a, **k):
            await asyncio.sleep(0.4)
            return await super().judge(*a, **k)

    ids = seed(pg)
    run(setup_saver(pg.app_url))
    env = WorkerEnv(factory=pg.factory, database_url=pg.app_url, make_brain=lambda row: Slow(usage=U),
                    search=FakeSearch(), min_slice_ms=0)
    app = app_for(pg, InlineEnqueuer(env), poll=0.1)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="error"))
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    port = server.servers[0].sockets[0].getsockname()[1]
    base, h = f"http://127.0.0.1:{port}", {"x-user": ids["user"]}
    try:
        r = httpx.post(f"{base}/debates", json=body(ids), headers=h)
        assert r.status_code == 202, r.text
        did = r.json()["id"]
        arrivals, raw = [], ""
        t0 = time.monotonic()
        with httpx.stream("GET", f"{base}/debates/{did}/events", headers=h, timeout=30) as resp:
            assert resp.headers["content-type"].startswith("text/event-stream")
            assert "no-transform" in resp.headers["cache-control"] and resp.headers["x-accel-buffering"] == "no"
            for chunk in resp.iter_text():
                now = time.monotonic() - t0
                for block in chunk.split("\n\n"):
                    if block.startswith(":"):
                        arrivals.append((now, "ping"))
                    elif "event: " in block:
                        arrivals.append((now, block.split("event: ")[1].split("\n")[0]))
                raw += chunk
                if "event: done" in chunk:
                    break
    finally:
        server.should_exit = True
        t.join(timeout=10)
    names = [n for _, n in arrivals if n != "ping"]
    assert names[0] == "state" and names[-1] == "done" and "completed" in names
    assert "data: {" in raw and "\nid: " in raw
    times = [a for a, n in arrivals if n not in ("ping",)]
    assert times[-1] - times[1] > 1.0, f"events were buffered and arrived together: {arrivals}"
    mid = [n for a, n in arrivals if 0.3 < a < times[-1] - 0.3 and n != "ping"]
    assert mid, f"nothing arrived while the debate was still running: {arrivals}"


# ---------- sharees: the project is copied to them and the debate runs in their copy ----------

def _share(pg, ids, sharee_id, revoked=False):
    pg.sql("INSERT INTO shares (project_id, shared_by_id, shared_with_id, revoked_at) VALUES (%s,%s,%s,%s)",
           (ids["project"], ids["user"], sharee_id, "2026-01-01" if revoked else None))


def _copy_project(pg, ids, sharee_id):
    """Stand-in for app.project_forking: copy project, tree and nodes to the sharee. Returns (project, node_map)."""
    pid = pg.sql("INSERT INTO projects (created_by_id, forked_from_project_id) VALUES (%s,%s) RETURNING id",
                 (sharee_id, ids["project"]))[0][0]
    tid = pg.sql("INSERT INTO trees (project_id) VALUES (%s) RETURNING id", (pid,))[0][0]
    node_map, parent = {}, None
    for old in ids["nodes"]:
        row = pg.sql("SELECT chats::text, fork_index FROM nodes WHERE id=%s", (old,))[0]
        new = pg.sql("INSERT INTO nodes (tree_id, project_id, parent_id, created_by_id, chats, fork_index) "
                     "VALUES (%s,%s,%s,%s,%s::jsonb,%s) RETURNING id", (tid, pid, parent, sharee_id, row[0], row[1]))[0][0]
        node_map[old], parent = str(new), new
    return str(pid), node_map


def _app_with_forking(pg, q, calls, **kw):
    from debate.pg.api import WriteTarget

    ids = kw.pop("ids")

    async def resolve(user, project, node):
        calls.append((user, project, node))
        pid, node_map = _copy_project(pg, ids, user)
        return WriteTarget(pid, node_map[node], {"project_id": pid, "node_id": node_map[node]})

    return app_for(pg, q, resolve_target=resolve, **kw)


def test_sharee_without_forking_configured_gets_403(pg):
    a, sharee = seed(pg), seed(pg)
    _share(pg, a, sharee["user"])

    async def go():
        async with client(app_for(pg, Queue())) as c:
            return (await c.post("/debates", json=body(a), headers=H(sharee["user"]))).status_code

    assert run(go()) == 403


def test_sharee_start_forks_and_the_debate_belongs_to_their_copy(pg):
    a, sharee, stranger = seed(pg), seed(pg), seed(pg)
    _share(pg, a, sharee["user"])
    q, calls = Queue(), []

    async def go():
        async with client(_app_with_forking(pg, q, calls, ids=a)) as c:
            assert (await c.post("/debates", json=body(a), headers=H(stranger["user"]))).status_code == 404  # not shared
            r = await c.post("/debates", json=body(a), headers=H(sharee["user"]))
            assert r.status_code == 202, r.text
            did, fork = r.json()["id"], r.json()["fork"]
            assert (await c.get(f"/debates/{did}", headers=H(sharee["user"]))).status_code == 200
            assert (await c.get(f"/debates/{did}", headers=H(a["user"]))).status_code == 404  # the owner can't see their copy's debates
            return did, fork

    did, fork = run(go())
    assert len(calls) == 1 and calls[0][0] == sharee["user"]
    row = pg.sql("SELECT owner_id::text, project_id::text, parent_node_id::text FROM debates WHERE id=%s", (did,))[0]
    assert row == (sharee["user"], fork["project_id"], fork["node_id"])
    assert row[1] != a["project"]
    assert pg.sql("SELECT count(*) FROM debates WHERE project_id=%s", (a["project"],))[0][0] == 0  # original untouched


def test_owner_start_never_calls_the_forking_hook_and_revoked_sharee_is_refused(pg):
    a, sharee = seed(pg), seed(pg)
    _share(pg, a, sharee["user"], revoked=True)
    q, calls = Queue(), []

    async def go():
        async with client(_app_with_forking(pg, q, calls, ids=a)) as c:
            assert (await c.post("/debates", json=body(a), headers=H(a["user"]))).status_code == 202
            assert (await c.post("/debates", json=body(a), headers=H(sharee["user"]))).status_code == 404

    run(go())
    assert calls == []


def test_the_active_cap_is_checked_before_a_sharee_project_is_copied(pg):
    a, sharee = seed(pg), seed(pg)
    _share(pg, a, sharee["user"])
    q, calls = Queue(), []

    async def go():
        async with client(_app_with_forking(pg, q, calls, ids=a, max_active_per_user=1)) as c:
            assert (await c.post("/debates", json=body(a), headers=H(sharee["user"]))).status_code == 202
            assert (await c.post("/debates", json=body(a), headers=H(sharee["user"]))).status_code == 429

    run(go())
    assert len(calls) == 1  # the refused request did not copy the project again


def test_debate_results_are_readable_by_active_sharees_only(pg):
    from debate.pg.adapters import PgWriter

    a, sharee, revoked, stranger = seed(pg), seed(pg), seed(pg), seed(pg)
    _share(pg, a, sharee["user"])
    _share(pg, a, revoked["user"], revoked=True)
    did = new_debate(pg, a)
    payload = {"proposition": "P", "winner": "for", "judge_would_have_chosen": "for", "confidence": 0.7, "summary": "s",
               "final_output": "f", "rationale": "r", "scores": {}, "end_reason": "rounds_exhausted"}
    node = run(PgWriter(pg.factory, a["user"]).create_result(did, payload))

    async def go():
        out = {}
        async with client(app_for(pg, Queue())) as c:
            for name, u in (("owner", a), ("sharee", sharee), ("revoked", revoked), ("stranger", stranger)):
                out[name] = (await c.get(f"/debates/node/{node}", headers=H(u["user"]))).status_code
        return out

    assert run(go()) == {"owner": 200, "sharee": 200, "revoked": 404, "stranger": 404}


# ---------------------------------------------------------------- branches: ticking them, and the nodes they become
BRANCHES = [
    Branch(title="Delivery speed vs cost", question="Do microservices-first startups ship faster?",
           why="Nobody measured it.", kind="research", from_claims=["A1"]),
    Branch(title="When releases matter", question="At what team size do independent releases pay off?",
           why="Asserted without a timeline.", kind="research"),
    Branch(title="Cost of migrating later", question="How expensive is decomposing at year two?",
           why="Never compared.", kind="debate"),
]


def finished_debate(pg, ids, branches=BRANCHES):
    """Run one debate to completion through the worker and return (debate_id, result_node_id)."""
    brain = ScriptedBrain(usage=U)
    brain.branches = list(branches) if branches is not None else None
    did = new_debate(pg, ids, rounds=1)
    run(run_debate(worker_env(pg, brain), did))
    node = pg.sql("SELECT result_node_id::text FROM debates WHERE id=%s", (did,))[0][0]
    assert node, "the debate did not finish"
    return did, node


def test_branches_are_stored_on_the_result_and_returned_by_the_node_endpoint(pg):
    ids = seed(pg)
    did, node = finished_debate(pg, ids)
    q = Queue()

    async def go():
        async with client(app_for(pg, q)) as c:
            r = await c.get(f"/debates/node/{node}", headers=H(ids["user"]))
            assert r.status_code == 200
            got = r.json()["branches"]
            assert [b["id"] for b in got] == ["b1", "b2", "b3"]
            assert got[0]["title"] == "Delivery speed vs cost" and got[2]["kind"] == "debate"
            assert all(b["selected"] is False and b["created_node_id"] is None for b in got)
    run(go())


def test_ticking_branches_persists_and_rejects_unknown_ids(pg):
    ids = seed(pg)
    did, node = finished_debate(pg, ids)
    q = Queue()

    async def go():
        async with client(app_for(pg, q)) as c:
            h = H(ids["user"])
            r = await c.patch(f"/debates/node/{node}/branches", json={"selected": ["b1", "b3"]}, headers=h)
            assert r.status_code == 200
            assert [b["id"] for b in r.json()["branches"] if b["selected"]] == ["b1", "b3"]
            # the full selection is sent each time, so this unticks b3
            r = await c.patch(f"/debates/node/{node}/branches", json={"selected": ["b1"]}, headers=h)
            assert [b["id"] for b in r.json()["branches"] if b["selected"]] == ["b1"]
            r = await c.patch(f"/debates/node/{node}/branches", json={"selected": ["nope"]}, headers=h)
            assert r.status_code == 422 and "unknown branch id" in r.json()["detail"]
            assert (await c.patch(f"/debates/node/{uuid.uuid4()}/branches", json={"selected": []}, headers=h)).status_code == 404
    run(go())


def test_creating_branches_makes_nodes_under_the_node_the_debate_started_from(pg):
    ids = seed(pg)
    did, node = finished_debate(pg, ids)
    origin = pg.sql("SELECT parent_node_id::text FROM debates WHERE id=%s", (did,))[0][0]
    q = Queue()

    async def go():
        async with client(app_for(pg, q)) as c:
            r = await c.post(f"/debates/node/{node}/branches", json={"ids": ["b1", "b3"]}, headers=H(ids["user"]))
            assert r.status_code == 201, r.text
            out = r.json()
            assert out["parent_node_id"] == origin
            return [x["node_id"] for x in out["created"]]

    made = run(go())
    assert len(made) == 2
    for nid in made:
        parent, ntype, dbid = pg.sql(
            "SELECT parent_id::text, node_type::text, branch_of_debate_id::text FROM nodes WHERE id=%s", (nid,))[0]
        assert parent == origin, "a branch hangs off the origin node, not the debate node"
        assert ntype == "standard", "a branch is an ordinary node, not another debate"
        assert dbid == did, "the node records which debate it came from"
    # the debate node is a sibling of the branches, not their parent
    assert pg.sql("SELECT parent_id::text FROM nodes WHERE id=%s", (node,))[0][0] == origin


def test_a_branch_node_cannot_see_its_siblings_through_its_lineage_or_its_seed(pg):
    ids = seed(pg)
    did, node = finished_debate(pg, ids)
    q = Queue()

    async def go():
        async with client(app_for(pg, q)) as c:
            r = await c.post(f"/debates/node/{node}/branches", json={"ids": ["b1", "b2", "b3"]}, headers=H(ids["user"]))
            assert r.status_code == 201
            return {x["branch_id"]: x["node_id"] for x in r.json()["created"]}

    made = run(go())
    by_branch = {b.id if b.id else f"b{i}": b for i, b in enumerate(BRANCHES, 1)}
    for i, (bid, nid) in enumerate(sorted(made.items()), 1):
        chats = pg.sql("SELECT chats FROM nodes WHERE id=%s", (nid,))[0][0]
        text_all = json.dumps(chats)
        mine = BRANCHES[i - 1]
        assert mine.question in text_all, "its own question must be seeded"
        for other in BRANCHES:
            if other.question != mine.question:
                assert other.question not in text_all, f"{bid} can see another branch's question"
                assert other.title not in text_all, f"{bid} can see another branch's title"
        # and no sibling is on its parent_id lineage either
        lineage = pg.sql(
            "WITH RECURSIVE up AS (SELECT id, parent_id FROM nodes WHERE id=%s "
            "UNION ALL SELECT n.id, n.parent_id FROM nodes n JOIN up ON n.id = up.parent_id) SELECT id::text FROM up", (nid,))
        got = {r[0] for r in lineage}
        assert not (set(made.values()) - {nid}) & got, "a sibling branch is on this node's lineage"


def test_creating_the_same_branch_twice_returns_the_first_node(pg):
    ids = seed(pg)
    did, node = finished_debate(pg, ids)
    q = Queue()

    async def go():
        async with client(app_for(pg, q)) as c:
            h = H(ids["user"])
            first = (await c.post(f"/debates/node/{node}/branches", json={"ids": ["b1"]}, headers=h)).json()
            again = (await c.post(f"/debates/node/{node}/branches", json={"ids": ["b1"]}, headers=h)).json()
            return first["created"][0], again["created"][0]

    a, b = run(go())
    assert a["created"] is True and b["created"] is False and a["node_id"] == b["node_id"]
    assert pg.sql("SELECT count(*) FROM nodes WHERE branch_of_debate_id=%s", (did,))[0][0] == 1


def test_creating_with_no_ids_uses_whatever_is_ticked(pg):
    ids = seed(pg)
    did, node = finished_debate(pg, ids)
    q = Queue()

    async def go():
        async with client(app_for(pg, q)) as c:
            h = H(ids["user"])
            assert (await c.post(f"/debates/node/{node}/branches", json={}, headers=h)).status_code == 422
            await c.patch(f"/debates/node/{node}/branches", json={"selected": ["b2"]}, headers=h)
            r = await c.post(f"/debates/node/{node}/branches", json={}, headers=h)
            assert r.status_code == 201
            return [x["branch_id"] for x in r.json()["created"]]

    assert run(go()) == ["b2"]


def test_another_user_cannot_read_or_branch_someone_elses_debate(pg):
    ids, other = seed(pg), seed(pg)
    did, node = finished_debate(pg, ids)
    q = Queue()

    async def go():
        async with client(app_for(pg, q)) as c:
            h = H(other["user"])
            assert (await c.get(f"/debates/node/{node}", headers=h)).status_code == 404
            assert (await c.patch(f"/debates/node/{node}/branches", json={"selected": ["b1"]}, headers=h)).status_code == 404
            assert (await c.post(f"/debates/node/{node}/branches", json={"ids": ["b1"]}, headers=h)).status_code == 404
    run(go())
    assert pg.sql("SELECT count(*) FROM nodes WHERE branch_of_debate_id=%s", (did,))[0][0] == 0


def test_a_debate_with_branching_off_stores_none(pg):
    ids = seed(pg)
    brain = ScriptedBrain(usage=U)
    brain.branches = list(BRANCHES)
    did = new_debate(pg, ids, rounds=1)
    run(run_debate(worker_env(pg, brain, max_branches=0), did))
    node = pg.sql("SELECT result_node_id::text FROM debates WHERE id=%s", (did,))[0][0]
    assert pg.sql("SELECT jsonb_array_length(branches) FROM debate_results WHERE node_id=%s", (node,))[0][0] == 0
