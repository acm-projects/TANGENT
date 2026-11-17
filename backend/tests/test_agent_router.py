"""POST /projects/:id/gent with the model, the tree and the database faked (runs in CI, no secrets)."""
import asyncio
import json
import os
import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

# app.database refuses to import without these; removed again after (see test_nodes_messages.py)
_dummies = {"DATABASE_URL": "postgresql://dummy@localhost/dummy", "JWT_SECRET_KEY": "test-secret"}
_added = [k for k in _dummies if k not in os.environ]
os.environ.update({k: _dummies[k] for k in _added})

from fastapi.testclient import TestClient

from app.agent import nudges
from app.agent import router as gent_router
from app.agent import tools
from app.auth import get_current_user
from app.database import get_db_session
from app.main import app

for _k in _added:
    del os.environ[_k]

from test_agent_tools import BASIC, tree  # noqa: E402  (the same faked tree)

PROJECT = uuid.uuid4()
USER = SimpleNamespace(id=uuid.uuid4())
MODEL = "nvidia/nemotron-3.5-lightning:free"


def call(id, name, args):
    return {"id": id, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}


def calls(*items):
    return {"tool_calls": list(items)}


def frames(body: str) -> list[tuple[str, dict]]:
    out = []
    for chunk in body.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in chunk.splitlines())
        out.append((lines["event"], json.loads(lines["data"])))
    return out


@pytest.fixture
def gent(monkeypatch):
    requests, ran = [], []
    script = []  # one list of stream events per model turn
    real_call = tools.call_tool

    class NoDb:
        async def rollback(self):
            pass

    async def no_db():
        yield NoDb()

    async def fake_stream(messages, model, transport=None, tools=None, tool_choice=None, reasoning=None):
        requests.append({"messages": [dict(m) for m in messages], "reasoning": reasoning, "tool_choice": tool_choice})
        for event in script.pop(0):
            yield event

    async def fake_call(run, name, args, on_step=None):
        if name in tools.NOTE_TOOLS or name == "think":
            return await real_call(run, name, args)
        ran.append((name, args))
        if name == "cat":
            return {"cwd": {"address": "1.1", "id": "a"}, "page": 1, "pages": 1, "content": "x" * 50}
        return {"cwd": {"address": "1", "id": "r"}}

    @asynccontextmanager
    async def session(user_id):
        yield None

    async def snapshot(db, project_id, user_id):
        return tree(*BASIC)

    async def owner(db, project_id, user):
        return None, "owner"

    app.dependency_overrides[get_current_user] = lambda: USER
    app.dependency_overrides[get_db_session] = no_db
    monkeypatch.setattr(gent_router, "stream_openrouter", fake_stream)
    monkeypatch.setattr(gent_router, "get_project_with_role", owner)
    monkeypatch.setattr(tools, "call_tool", fake_call)
    monkeypatch.setattr(tools, "_session", session)
    monkeypatch.setattr(tools, "snapshot", snapshot)
    with TestClient(app) as c:
        def post(content="Research long context", **extra):
            r = c.post(f"/projects/{PROJECT}/gent",
                       json={"messages": [{"role": "user", "content": content}], "model": MODEL, **extra})
            return r if r.status_code != 200 else SimpleNamespace(status_code=200, events=frames(r.text))
        yield SimpleNamespace(c=c, post=post, script=script, requests=requests, ran=ran)
    app.dependency_overrides.clear()


def test_plans_works_and_reports(gent):
    gent.script += [
        [{"text": "Plan first."}, calls(call("1", "todo_add", {"tasks": ["Map the tree", "Ask the angles"]}))],
        [{"text": "Look around."}, calls(call("2", "ls", {}), call("3", "todo_tick", {}))],
        [calls(call("4", "bulk_ask", {"under": ".", "questions": [{"question": "q"}]}), call("5", "todo_tick", {}))],
        [{"text": "Answers are in 1.3 and 1.4."}],
    ]
    out = gent.post(active_node_id=None)
    kinds = [e for e, _ in out.events]
    assert kinds[:2] == ["cwd", "notes"] and kinds[-2:] == ["reply", "done"]
    assert ("reply", {"turn": 4, "text": "Answers are in 1.3 and 1.4."}) in out.events
    assert [name for name, _ in gent.ran] == ["ls", "bulk_ask"]
    notes = [d for e, d in out.events if e == "notes"][-1]["notes"]
    assert [(n["id"], n["done"]) for n in notes] == [("n1", True), ("n2", True)]
    results = [d for e, d in out.events if e == "result"]
    assert results[0]["brief"] == "updated the Field Notes" and results[1]["brief"] == "listed 0 branches at 1"
    notes_text = "".join(d["text"] for e, d in out.events if e == "note")
    assert notes_text == "Plan first.Look around.Answers are in 1.3 and 1.4."  # the last turn's is the reply
    system = gent.requests[1]["messages"][0]["content"]
    assert "You are at: 1 R" in system and "n1 [ ] Map the tree   (current)" in system


def test_open_tasks_are_sent_back_three_times_then_he_may_stop(gent):
    gent.script += [
        [calls(call("1", "todo_add", {"tasks": ["One", "Two"]}))],
        [{"text": "Done."}],  # quits with both open
        [{"text": "Done."}],
        [{"text": "Done."}],
        [{"text": "Still done."}],
    ]
    out = gent.post()
    assert 'still open: n1 "One"; n2 "Two"' in gent.requests[2]["messages"][-1]["content"]
    assert "last reminder" in gent.requests[4]["messages"][-1]["content"]
    assert ("reply", {"turn": 5, "text": "Still done."}) in out.events  # not sent back a fourth time


def test_a_long_reply_is_sent_back_then_cut(gent):
    long = "word " * 200
    gent.script += [[{"text": long}], [{"text": long}]]
    out = gent.post()
    assert gent.requests[1]["messages"][-1]["content"] == nudges.TOO_LONG
    reply = [d["text"] for e, d in out.events if e == "reply"][0]
    assert len(reply) <= nudges.REPLY_CHARS + 1 and reply.endswith("…")


def test_think_turns_reasoning_on_for_the_next_turn_only(gent):
    gent.script += [
        [calls(call("1", "think", {"depth": "deep"}))],
        [{"reasoning": "weighing it"}, {"reasoning_details": [{"type": "reasoning.text", "text": "weighing it"}]},
         calls(call("2", "ls", {}))],
        [{"text": "Hi."}],
    ]
    out = gent.post(content="hi")
    assert [r["reasoning"] for r in gent.requests] == [{"effort": "low"}, {"effort": "high"}, {"effort": "low"}]
    assert ("reasoning", {"turn": 2, "depth": "deep", "text": "weighing it"}) in out.events
    turn2 = gent.requests[2]["messages"]
    assert any(m.get("reasoning_details") for m in turn2)  # kept and sent back
    assert [d["brief"] for e, d in out.events if e == "result"][0] == "thought deeply"


def test_a_shared_project_already_copied_redirects(gent, monkeypatch):
    async def shared(db, project_id, user):
        return None, "shared"

    async def copy(db, project_id, user_id):
        return SimpleNamespace(id=uuid.uuid4())

    monkeypatch.setattr(gent_router, "get_project_with_role", shared)
    monkeypatch.setattr(gent_router, "get_user_copy", copy)
    r = gent.post()
    assert r.status_code == 409 and "forked_project_id" in r.json()["detail"]


def test_model_failure_is_retried_then_ends_the_run(gent, monkeypatch):
    monkeypatch.setattr(gent_router, "RETRY_WAIT", 0)
    gent.script += [[{"error": {"message": "overloaded"}}]] * gent_router.MODEL_TRIES
    out = gent.post()
    assert out.events[-1] == ("error", {"message": "The model failed: overloaded"})


def test_a_provider_hiccup_before_anything_streamed_is_retried(gent, monkeypatch):
    monkeypatch.setattr(gent_router, "RETRY_WAIT", 0)
    gent.script += [[{"error": {"message": "inference generation failed"}}], [{"text": "Hello."}]]
    out = gent.post()
    assert ("error", {"message": "The model failed: inference generation failed"}) not in out.events
    assert out.events[-1][0] == "done"


def test_stop_and_notes_reach_a_running_gent(monkeypatch):
    """Drive the loop directly: a user edit lands before the next turn, and stop ends it mid-run."""
    seen, turns = [], asyncio.Queue()

    async def fake_stream(messages, model, transport=None, tools=None, tool_choice=None, reasoning=None):
        seen.append(messages)
        await turns.get()
        yield calls(call(str(len(seen)), "get_todo", {}))

    async def snapshot(db, project_id, user_id):
        return tree(*BASIC)

    @asynccontextmanager
    async def session(user_id):
        yield None

    monkeypatch.setattr(gent_router, "stream_openrouter", fake_stream)
    monkeypatch.setattr(tools, "snapshot", snapshot)
    monkeypatch.setattr(tools, "_session", session)

    async def scenario():
        run = tools.Run(project_id=PROJECT, user_id=USER.id, model=MODEL, cwd="r", owner=True,
                        notes=[{"id": "n1", "text": "Map", "done": False}])
        task = asyncio.create_task(gent_router.work(run, [{"role": "user", "content": "go"}]))
        turns.put_nowait(None)
        while len(seen) < 2:
            await asyncio.sleep(0)
        # the user edits while turn 2 is streaming: Gent hears it at turn 3
        new = gent_router.with_ids([{"id": "n1", "text": "Map", "done": True}, {"id": None, "text": "Added"}])
        run.user_edits.append(gent_router.describe_edits(run.notes, new))
        run.notes[:] = new
        turns.put_nowait(None)
        while len(seen) < 3:
            await asyncio.sleep(0)
        told = [m["content"] for m in seen[2] if m["role"] == "user"][-1]
        task.cancel()  # what stop does
        return told

    told = asyncio.run(scenario())
    assert told.startswith('(The user edited your Field Notes: added n2 "Added"; ticked n1.)')


def test_with_ids_and_describe_edits():
    notes = gent_router.with_ids([{"id": "n1", "text": "a"}, {"text": "b"}, {"id": "n1", "text": "c"}])
    assert [n["id"] for n in notes] == ["n1", "n2", "n3"]
    # who wrote an item survives the round trip; an unknown author stays unknown
    kept = gent_router.with_ids([gent_router.GentNote(text="mine", by="user"), gent_router.GentNote(id="n1", text="his", by="gent"),
                                 gent_router.GentNote(text="old")])
    assert [n.get("by") for n in kept] == ["user", "gent", None]
    before = [{"id": "n1", "text": "a", "done": False}, {"id": "n2", "text": "b", "done": False}]
    after = [{"id": "n1", "text": "A", "done": True}, {"id": "n3", "text": "new", "done": False}]
    assert gent_router.describe_edits(before, after) == 'added n3 "new"; struck n2 "b"; reworded n1 to "A"; ticked n1'
    assert gent_router.describe_edits(before, before) == ""


def _tool_turn(i, name, content="x" * 100, note=None):
    return ([{"role": "assistant", "content": f"note {i}", "tool_calls": [call(str(i), name, {})]},
             {"role": "tool", "tool_call_id": str(i), "content": content}],
            [None, {"name": name, "brief": f"{name} {i}", "note": note}])


def _convo(*turns):
    convo, meta = [{"role": "user", "content": "task"}], [None]
    for c, m in turns:
        convo += c
        meta += m
    return convo, meta


def test_hygiene_keeps_the_last_keep_cats_cats():
    k = gent_router.KEEP_CATS
    convo, meta = _convo(*(_tool_turn(i, "cat") for i in range(k + 2)), _tool_turn(99, "ls"))
    out = gent_router.hygiene(convo, meta, [], budget_chars=10**9)
    tool_contents = [m["content"] for m in out if m["role"] == "tool"]
    assert "folded" in tool_contents[0] and "cat 0; cd there and cat again" in tool_contents[0]
    assert "folded" in tool_contents[1]
    assert tool_contents[2:] == ["x" * 100] * (k + 1)  # the last KEEP_CATS cats, and the ls
    assert convo[2]["content"] == "x" * 100  # the run's own copy is untouched


def test_hygiene_folds_resolved_tasks_to_their_briefs():
    convo, meta = _convo(_tool_turn(1, "ls", note="n1"), _tool_turn(2, "ls", note="n2"))
    out = gent_router.hygiene(convo, meta, [{"id": "n1", "done": True}, {"id": "n2", "done": False}], 10**9)
    assert json.loads(out[2]["content"]) == {"folded": "ls 1"}
    assert out[4]["content"] == "x" * 100


def test_hygiene_folds_the_oldest_past_the_budget_but_not_the_move_in_progress():
    convo, meta = _convo(*(_tool_turn(i, "ls") for i in range(5)))
    out = gent_router.hygiene(convo, meta, [], budget_chars=900)
    assert "folded" in out[2]["content"]
    assert out[-1]["content"] == "x" * 100  # the latest result stays whole
    assert [m["role"] for m in out] == [m["role"] for m in convo]  # pairing intact


def test_updates_are_delivered_before_the_next_move():
    run = tools.Run(project_id=PROJECT, user_id=USER.id, model=MODEL, cwd="r", owner=True)
    run.post({"kind": "answer", "address": "1.3", "id": "x", "preview": "Sparse attention scales."})
    run.post({"kind": "user", "text": "Skip retrieval."})
    run.post({"kind": "answer", "address": "1.4", "id": "y", "error": "The model failed"})
    out = gent_router.delivered(run)
    assert out == [
        {"role": "user", "content": "Skip retrieval."},
        {"role": "user", "content": "(Answers that came in: 1.3 answered: Sparse attention scales.\n1.4 failed: The model failed (ask(1.4, …) again to retry; don't delete it))"},
    ]
    assert run.updates == [] and gent_router.delivered(run) == []


def test_finishing_while_nodes_answer_is_nudged_once(gent, monkeypatch):
    async def fake_call(run, name, args, on_step=None):
        run.asking["n9"] = "1.9"  # an ask still running
        return {"cwd": {"address": "1", "id": "r"}, "asking": True}

    monkeypatch.setattr(tools, "call_tool", fake_call)
    gent.script += [[calls(call("1", "ask", {"card": ".", "question": "q"}))], [{"text": "Done."}], [{"text": "Done anyway."}]]
    out = gent.post()
    assert "1.9 are still answering" in gent.requests[2]["messages"][-1]["content"]
    assert ("reply", {"turn": 3, "text": "Done anyway."}) in out.events


def test_messages_need_a_running_gent(gent):
    r = gent.c.post(f"/projects/{PROJECT}/gent/message", json={"content": "hello"})
    assert r.status_code == 409
    run = tools.Run(project_id=PROJECT, user_id=USER.id, model=MODEL, cwd="r", owner=True)
    gent_router._runs[(USER.id, PROJECT)] = run
    try:
        assert gent.c.post(f"/projects/{PROJECT}/gent/message", json={"content": "hello"}).status_code == 202
        assert run.updates == [{"kind": "user", "text": "hello"}] and run.arrived.is_set()
    finally:
        del gent_router._runs[(USER.id, PROJECT)]


def test_field_notes_check_in_after_moves_without_an_update(gent):
    gent.script += [
        [calls(call("1", "todo_add", {"tasks": ["Survey the options", "Branch them"]}))],
        [calls(*(call(f"m{i}", "ls", {}) for i in range(3)))],
        [calls(*(call(f"n{i}", "ls", {}) for i in range(3)))],  # six moves, no update
        [calls(call("2", "todo_tick", {}))],
        [calls(call("3", "ls", {}))],
        [{"text": "Done."}],
        [{"text": "Done."}],
    ]
    gent.post()
    users = lambda turn: [m["content"] for m in gent.requests[turn]["messages"] if m["role"] == "user"]
    assert not any("Field Notes check" in m for m in users(2))
    assert users(3)[-1] == nudges.CHECK_IN.format(id="n1", text="Survey the options")
    assert sum("Field Notes check" in m for m in users(5)) == 1  # resolving reset the count
    tool_msg = next(m for m in gent.requests[2]["messages"] if m["role"] == "tool" and m["tool_call_id"] == "m0")
    assert json.loads(tool_msg["content"])["current_task"] == "n1 Survey the options"


def test_nudges_reach_the_client_too(gent):
    gent.script += [[{"text": "word " * 200}], [{"text": "Short."}]]
    out = gent.post()
    assert ("nudge", {"turn": 1, "name": "too_long", "text": nudges.TOO_LONG}) in out.events


def test_splitting_the_question_again_at_the_top_is_nudged_in_the_result(gent):
    gent.script += [
        [calls(call("1", "bulk_ask", {"under": ".", "questions": ["a", "b"]}))],
        [calls(call("2", "bulk_ask", {"under": ".", "questions": ["c"]}))],  # back at the start card ("1")
        [{"text": "Done."}],
    ]
    out = gent.post()
    told = [d for e, d in out.events if e == "nudge"]
    assert [d["name"] for d in told] == ["back_up"] and told[0]["turn"] == 2
    assert "Go deeper instead" in gent.requests[2]["messages"][-1]["content"]  # Gent reads it in the tool result


def test_out_of_moves_he_wraps_up_then_must_reply(gent, monkeypatch):
    monkeypatch.setattr(gent_router, "MAX_MOVES", 3)
    monkeypatch.setattr(gent_router, "WRAP_UP_AT", 2)
    gent.script += [[calls(call(str(i), "ls", {}))] for i in range(3)]
    gent.script += [[{"text": "Found 1.1; 1.2 is still open."}, calls(call("9", "ls", {}))]]  # tries once more
    out = gent.post()
    names = [d["name"] for e, d in out.events if e == "nudge"]
    assert "wrap_up" in names and "out_of_moves" in names
    assert gent.requests[-1]["tool_choice"] == "none" and gent.requests[0]["tool_choice"] is None
    assert ("reply", {"turn": 4, "text": "Found 1.1; 1.2 is still open."}) in out.events
    assert len(gent.ran) == 3  # the call he tried after running out was never made
