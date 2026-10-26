"""POST /nodes/:id/messages with the provider and the database faked (runs in CI, no secrets)."""
import asyncio
import json
import os
import uuid
from types import SimpleNamespace

import httpx
import pytest

# app.database refuses to import without these; the engine connects lazily, so dummies are enough.
# They are removed again after the import below: the real-DB test modules skip themselves when these
# are unset, and would otherwise see the dummies (collected after this file) and try to connect.
_dummies = {"DATABASE_URL": "postgresql://dummy@localhost/dummy", "JWT_SECRET_KEY": "test-secret"}
_added = [k for k in _dummies if k not in os.environ]
os.environ.update({k: _dummies[k] for k in _added})

from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.auth import get_current_user
from app.context.schemas import PathNode
from app.core import openrouter
from app.database import get_db_session
from app.main import app
from app.routers import nodes_router

for _k in _added:
    del os.environ[_k]

NODE = uuid.uuid4()
PROJECT = uuid.uuid4()
USER = SimpleNamespace(id=uuid.uuid4())


def provider(sse_lines: list[str], status: int = 200):
    """Fake OpenRouter; also records the request body it was sent."""
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(status, text="\n\n".join(sse_lines) + "\n\n")

    return httpx.MockTransport(handler), seen


def chunk(text=None, usage=None):
    d = {"model": "m", "choices": [{"delta": {"content": text}}] if text else []}
    if usage:
        d["usage"] = usage
    return "data: " + json.dumps(d)


def fork_payload(node_id):
    """What _prepare_write returns for a sharee's first write: the copy's id for the prompted node, plus the fork info."""
    return {
        "project_id": str(uuid.uuid4()),
        "workspace_slug": "my-workspace",
        "node_map": {str(NODE): str(node_id)},
        "tree_map": {},
        "node_id": str(node_id),
    }


@pytest.fixture
def client(monkeypatch):
    persisted = []
    prepare = {"result": None, "error": None, "calls": []}

    class NoDb:
        async def rollback(self):  # send_message releases the request's connection before streaming
            pass

    async def no_db():
        yield NoDb()

    async def fake_prepare(user_id, project_id, node_id):
        prepare["calls"].append((user_id, project_id, node_id))
        if prepare["error"] is not None:
            raise prepare["error"]
        return prepare["result"] or (node_id, None)

    async def fake_persist(
        user_id, write_node_id, user_text, assistant_text, model_id, response_tokens, replace_last=False
    ):
        persisted.append(
            (user_id, write_node_id, user_text, assistant_text, model_id, response_tokens)
            + (("replace",) if replace_last else ())
        )

    async def fake_path(db, node_id, user_id):
        return [PathNode(id="root", chats=[
            {"role": "user", "content": "earlier q", "seq": 0, "created_at": "2026-01-01T00:00:00Z"},
            {"role": "assistant", "content": "earlier a", "seq": 1, "created_at": "2026-01-01T00:00:01Z"},
        ])], PROJECT

    app.dependency_overrides[get_current_user] = lambda: USER
    app.dependency_overrides[get_db_session] = no_db
    monkeypatch.setattr(nodes_router, "_prepare_write", fake_prepare)
    monkeypatch.setattr(nodes_router, "_persist", fake_persist)
    monkeypatch.setattr(nodes_router, "_load_path", fake_path)

    async def no_uploads(project_id):
        return ""

    monkeypatch.setattr(nodes_router.paper_service, "project_sources_note", no_uploads)
    c = TestClient(app)
    c.persisted = persisted
    c.prepare = prepare
    yield c
    app.dependency_overrides.clear()


def use_provider(monkeypatch, transport):
    real = openrouter.stream_openrouter
    monkeypatch.setattr(
        nodes_router, "stream_openrouter", lambda msgs, model, **kw: real(msgs, model, transport=transport, **kw)
    )


def events(resp):
    out = []
    for frame in resp.text.strip().split("\n\n"):
        name, data = frame.split("\n")
        out.append((name.removeprefix("event: "), json.loads(data.removeprefix("data: "))))
    return out


def test_streams_tokens_sends_history_and_persists(client, monkeypatch):
    usage = {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7}
    transport, seen = provider([chunk("Hel"), chunk("lo"), chunk(usage=usage), "data: [DONE]"])
    use_provider(monkeypatch, transport)

    r = client.post(f"/nodes/{NODE}/messages", json={"content": "hi"})

    assert r.status_code == 200
    assert events(r) == [
        ("token", {"text": "Hel"}),
        ("token", {"text": "lo"}),
        ("done", {"usage": usage, "model": "m"}),
    ]
    assert [m["content"] for m in seen["body"]["messages"] if m["role"] != "system"] == ["earlier q", "earlier a", "hi"]
    assert client.persisted == [
        (USER.id, NODE, "hi", "Hello", openrouter.DEFAULT_MODEL_ID, 7)
    ]
    assert client.prepare["calls"] == [(USER.id, PROJECT, NODE)]


def test_provider_error_is_an_error_event_and_saves_nothing(client, monkeypatch):
    transport, _ = provider(["rate limited"], status=429)
    use_provider(monkeypatch, transport)

    r = client.post(f"/nodes/{NODE}/messages", json={"content": "hi"})

    assert events(r) == [("error", {"message": "rate limited\n\n"})]
    assert client.persisted == []


def test_sharee_first_message_saves_into_the_copy_and_done_carries_fork(client, monkeypatch):
    copy_node = uuid.uuid4()
    fork = fork_payload(copy_node)
    client.prepare["result"] = (copy_node, fork)
    usage = {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7}
    transport, _ = provider([chunk("Hi"), chunk(usage=usage), "data: [DONE]"])
    use_provider(monkeypatch, transport)

    r = client.post(f"/nodes/{NODE}/messages", json={"content": "hi"})

    assert events(r) == [
        ("token", {"text": "Hi"}),
        ("done", {"usage": usage, "model": "m", "fork": fork}),
    ]
    # written into the copy's node, never the original
    assert client.persisted == [
        (USER.id, copy_node, "hi", "Hi", openrouter.DEFAULT_MODEL_ID, 7)
    ]


def test_error_after_the_fork_still_carries_it(client, monkeypatch):
    # The project is copied before the model is called, so a provider failure must not hide the copy from the client.
    copy_node = uuid.uuid4()
    fork = fork_payload(copy_node)
    client.prepare["result"] = (copy_node, fork)
    transport, _ = provider(["rate limited"], status=429)
    use_provider(monkeypatch, transport)

    r = client.post(f"/nodes/{NODE}/messages", json={"content": "hi"})

    assert events(r) == [("error", {"message": "rate limited\n\n", "fork": fork})]
    assert client.persisted == []


def test_existing_copy_409_is_an_error_event_with_the_copy_id_and_no_model_call(client, monkeypatch):
    copy_id = str(uuid.uuid4())
    detail = {"message": "You already have your own copy of this project. Edit that one.", "forked_project_id": copy_id}
    client.prepare["error"] = HTTPException(409, detail=detail)
    transport, seen = provider([chunk("Hi"), "data: [DONE]"])
    use_provider(monkeypatch, transport)

    r = client.post(f"/nodes/{NODE}/messages", json={"content": "hi"})

    assert events(r) == [("error", detail)]
    assert "body" not in seen  # the model was never called
    assert client.persisted == []


def test_unknown_model_is_400(client):
    r = client.post(f"/nodes/{NODE}/messages", json={"content": "hi", "model": "nope"})
    assert r.status_code == 400


def test_requires_auth():
    r = TestClient(app).post(f"/nodes/{NODE}/messages", json={"content": "hi"})
    assert r.status_code in (401, 403)


class FakeDb:
    """Stands in for the session. Results come back in call order: the path query, the has_child/owner/project flags,
    then (non-owners only) the lookup of the user's existing copy of the project."""

    def __init__(self, path_rows, has_child=False, is_owner=True, copy_id=None):
        flags = SimpleNamespace(
            has_child=has_child,
            owner_id=USER.id if is_owner else uuid.uuid4(),
            project_id=PROJECT,
        )
        copy = SimpleNamespace(id=copy_id) if copy_id else None
        self.results = [
            SimpleNamespace(all=lambda: path_rows),
            SimpleNamespace(one=lambda: flags),
            SimpleNamespace(scalar_one_or_none=lambda: copy),
        ]

    async def execute(self, *_):
        return self.results.pop(0)


async def load(db):
    return await nodes_router._load_path(db, NODE, USER.id)


@pytest.mark.anyio
async def test_load_path_404_when_node_missing_or_hidden():
    with pytest.raises(HTTPException) as e:
        await load(FakeDb([]))
    assert e.value.status_code == 404


@pytest.mark.anyio
async def test_load_path_409_for_non_leaf():
    with pytest.raises(HTTPException) as e:
        await load(FakeDb([SimpleNamespace(id="a", chats=[])], has_child=True))
    assert e.value.status_code == 409


@pytest.mark.anyio
async def test_load_path_owner_gets_path_and_project_id():
    path, project_id = await load(FakeDb([SimpleNamespace(id="a", chats=[])]))
    assert [p.id for p in path] == ["a"]
    assert project_id == PROJECT


@pytest.mark.anyio
async def test_load_path_sharee_without_a_copy_may_prompt():
    # A sharee's first write forks the project, so reading the original's path must be allowed.
    path, project_id = await load(FakeDb([SimpleNamespace(id="a", chats=[])], is_owner=False))
    assert project_id == PROJECT


@pytest.mark.anyio
async def test_load_path_sharee_with_a_copy_gets_409_pointing_at_it():
    copy_id = uuid.uuid4()
    with pytest.raises(HTTPException) as e:
        await load(FakeDb([SimpleNamespace(id="a", chats=[])], is_owner=False, copy_id=copy_id))
    assert e.value.status_code == 409
    assert e.value.detail["forked_project_id"] == str(copy_id)


@pytest.fixture
def anyio_backend():
    return "asyncio"

def test_stop_saves_what_arrived_and_ends_with_done_stopped(client, monkeypatch):
    async def slow(msgs, model, **_):
        yield {"text": "Hel"}
        nodes_router._stops[(USER.id, NODE)].set()  # the user presses Stop mid-reply
        await asyncio.sleep(10)
        yield {"text": "never"}

    monkeypatch.setattr(nodes_router, "stream_openrouter", slow)

    r = client.post(f"/nodes/{NODE}/messages", json={"content": "hi"})

    assert events(r) == [("token", {"text": "Hel"}), ("done", {"stopped": True})]
    assert client.persisted == [
        (USER.id, NODE, "hi", "Hel", openrouter.DEFAULT_MODEL_ID, None)
    ]
    assert (USER.id, NODE) not in nodes_router._stops


def test_stop_before_any_token_saves_nothing(client, monkeypatch):
    async def silent(msgs, model, **_):
        nodes_router._stops[(USER.id, NODE)].set()
        await asyncio.sleep(10)
        yield {"text": "never"}

    monkeypatch.setattr(nodes_router, "stream_openrouter", silent)

    r = client.post(f"/nodes/{NODE}/messages", json={"content": "hi"})

    assert events(r) == [("done", {"stopped": True})]
    assert client.persisted == []


def test_stop_endpoint_is_a_no_op_when_nothing_streams(client):
    assert client.post(f"/nodes/{NODE}/messages/stop").status_code == 204


def test_retry_reasks_the_last_question_without_the_old_reply_and_replaces_it(client, monkeypatch):
    transport, seen = provider([chunk("Again"), "data: [DONE]"])
    use_provider(monkeypatch, transport)

    r = client.post(f"/nodes/{NODE}/messages", json={"content": "ignored", "retry": True})

    assert events(r) == [("token", {"text": "Again"}), ("done", {})]
    # the stored question is re-asked, and the reply being replaced isn't in the context
    assert [m["content"] for m in seen["body"]["messages"] if m["role"] != "system"] == ["earlier q"]
    assert client.persisted == [
        (USER.id, NODE, "earlier q", "Again", openrouter.DEFAULT_MODEL_ID, None, "replace")
    ]


def test_node_rejects_a_different_model_before_calling_provider(client, monkeypatch):
    async def locked_path(db, node_id, user_id):
        return [nodes_router.PathNode(id="root", chats=[], model="locked-model")], PROJECT

    monkeypatch.setattr(nodes_router, "_load_path", locked_path)
    transport, seen = provider([chunk("Should not run"), "data: [DONE]"])
    use_provider(monkeypatch, transport)

    r = client.post(
        f"/nodes/{NODE}/messages",
        json={"content": "hi", "model": openrouter.DEFAULT_MODEL_ID},
    )

    assert r.status_code == 409
    assert "locked to model locked-model" in r.json()["detail"]
    assert "body" not in seen
    assert client.persisted == []


def test_retry_with_no_reply_to_replace_is_refused(client, monkeypatch):
    async def bare_path(db, node_id, user_id):
        return [nodes_router.PathNode(id="root", chats=[])], PROJECT

    monkeypatch.setattr(nodes_router, "_load_path", bare_path)

    r = client.post(f"/nodes/{NODE}/messages", json={"content": "x", "retry": True})

    assert r.status_code == 409
    assert client.persisted == []


def tool_chunk(id=None, name=None, args=""):
    fn = {"arguments": args, **({"name": name} if name else {})}
    call = {"index": 0, "function": fn, **({"id": id} if id else {})}
    return "data: " + json.dumps({"model": "m", "choices": [{"delta": {"tool_calls": [call]}}]})


def scripted_provider(responses):
    """Fake OpenRouter that answers each request with the next response; records every request body."""
    bodies, replies = [], iter(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(200, text="\n\n".join(next(replies)) + "\n\n")

    return httpx.MockTransport(handler), bodies


EVIDENCE = {"paper_id": "p1", "title": "T", "truncated": False,
            "evidence": [{"evidence_id": "p1:c0", "section": "2 Method", "pages": "3", "text": "We rank with BM25."}]}


def test_tool_call_round_then_cited_answer(client, monkeypatch):
    transport, bodies = scripted_provider([
        [tool_chunk("call_1", "search_paper_evidence", '{"paper_id": "p1", '), tool_chunk(args='"query": "rank"}'),
         "data: [DONE]"],
        [chunk("Ranks with BM25 [p1:c0], see also [p9:c9]."), "data: [DONE]"],
    ])
    use_provider(monkeypatch, transport)
    calls = []

    async def fake_tool(name, args, project_id):
        calls.append((name, args, project_id))
        return EVIDENCE

    monkeypatch.setattr(nodes_router.paper_service, "call_tool", fake_tool)

    r = client.post(f"/nodes/{NODE}/messages", json={"content": "how do they rank?"})

    evs = events(r)
    assert evs[0] == ("tool", {"name": "search_paper_evidence"})
    assert evs[-1] == ("done", {
        "citations": [{"evidence_id": "p1:c0", "title": "T", "pages": "3"}],
        "unverified_citations": ["p9:c9"],  # cited, but no tool returned it this turn
    })
    assert calls == [("search_paper_evidence", {"paper_id": "p1", "query": "rank"}, PROJECT)]
    assert bodies[0]["tools"] and bodies[0]["messages"][0]["role"] == "system"
    sent = bodies[1]["messages"]
    assert sent[-2]["tool_calls"][0]["function"] == {
        "name": "search_paper_evidence", "arguments": '{"paper_id": "p1", "query": "rank"}'}
    assert sent[-1]["role"] == "tool" and sent[-1]["tool_call_id"] == "call_1"
    assert json.loads(sent[-1]["content"]) == EVIDENCE
    assert client.persisted[0][3] == "Ranks with BM25 [p1:c0], see also [p9:c9]."


def test_tool_rounds_are_bounded(client, monkeypatch):
    forever = [tool_chunk("c", "search_papers", '{"query": "x"}'), "data: [DONE]"]
    transport, bodies = scripted_provider([forever] * (nodes_router.MAX_TOOL_ROUNDS + 1))
    use_provider(monkeypatch, transport)
    calls = []

    async def fake_tool(name, args, project_id):
        calls.append(name)
        return {"results": []}

    monkeypatch.setattr(nodes_router.paper_service, "call_tool", fake_tool)

    r = client.post(f"/nodes/{NODE}/messages", json={"content": "loop"})

    assert len(calls) == nodes_router.MAX_TOOL_ROUNDS
    assert len(bodies) == nodes_router.MAX_TOOL_ROUNDS + 1
    assert bodies[-1]["tool_choice"] == "none" and "tool_choice" not in bodies[0]
    assert events(r)[-1][0] == "error"  # never answered: nothing saved
    assert client.persisted == []


def test_bad_tool_arguments_go_back_to_the_model(client, monkeypatch):
    transport, bodies = scripted_provider([
        [tool_chunk("c", "get_paper", "{not json"), "data: [DONE]"],
        [chunk("Sorry."), "data: [DONE]"],
    ])
    use_provider(monkeypatch, transport)

    r = client.post(f"/nodes/{NODE}/messages", json={"content": "x"})

    assert events(r)[-1][0] == "done"
    assert "not valid JSON" in bodies[1]["messages"][-1]["content"]


def test_parallel_tool_calls_are_capped_per_round(client, monkeypatch):
    many = [tool_chunk(f"c{i}", "search_papers", '{"query": "x"}').replace('"index": 0', f'"index": {i}')
            for i in range(nodes_router.MAX_CALLS_PER_ROUND + 2)]
    transport, bodies = scripted_provider([many + ["data: [DONE]"], [chunk("ok"), "data: [DONE]"]])
    use_provider(monkeypatch, transport)
    calls = []

    async def fake_tool(name, args, project_id):
        calls.append(name)
        return {"results": []}

    monkeypatch.setattr(nodes_router.paper_service, "call_tool", fake_tool)

    r = client.post(f"/nodes/{NODE}/messages", json={"content": "x"})

    assert events(r)[-1][0] == "done" and len(calls) == nodes_router.MAX_CALLS_PER_ROUND
    replies = [m for m in bodies[1]["messages"] if m["role"] == "tool"]
    assert len(replies) == nodes_router.MAX_CALLS_PER_ROUND + 2  # every call answered
    assert "skipped" in replies[-1]["content"]


def test_system_prompt_names_project_uploads(client, monkeypatch):
    """Regression: an uploaded PDF was invisible to the model (search_papers only matches titles/abstracts),
    so it asked the user to clarify instead of searching the upload's evidence."""
    asked = []

    async def fake_note(project_id):
        asked.append(project_id)
        return nodes_router.paper_service.sources_note([
            {"id": 38, "title": "00 Assignment Submit Policy and Rules.pdf", "status": "ready",
             "pdf_url": None, "pdf_sha256": "abc"},
        ])

    monkeypatch.setattr(nodes_router.paper_service, "project_sources_note", fake_note)
    transport, seen = provider([chunk("ok"), "data: [DONE]"])
    use_provider(monkeypatch, transport)

    client.post(f"/nodes/{NODE}/messages", json={"content": "What are the rules for my submissions?"})

    assert asked == [PROJECT]
    system = seen["body"]["messages"][0]
    assert system["role"] == "system" and system["content"].startswith(nodes_router.paper_service.RESEARCH_SYSTEM_PROMPT)
    assert "- p38: 00 Assignment Submit Policy and Rules.pdf (full_text: ready)" in system["content"]
    assert "search_paper_evidence" in system["content"].split("p38", 1)[1]


def test_provider_5xx_before_any_text_is_retried_once(client, monkeypatch):
    err = "data: " + json.dumps({"error": {"message": "Provider returned error", "code": 502}})
    transport, bodies = scripted_provider([[err], [chunk("hello"), "data: [DONE]"]])
    use_provider(monkeypatch, transport)

    r = client.post(f"/nodes/{NODE}/messages", json={"content": "hi"})

    assert [e[0] for e in events(r)] == ["token", "done"] and len(bodies) == 2


def test_persistent_provider_5xx_is_a_plain_message_not_raw_json(client, monkeypatch):
    err = "data: " + json.dumps({"error": {"message": "Provider returned error", "code": 502, "metadata": {"raw": "x"}}})
    transport, bodies = scripted_provider([[err], [err]])
    use_provider(monkeypatch, transport)

    r = client.post(f"/nodes/{NODE}/messages", json={"content": "hi"})

    assert events(r) == [("error", {"message": "The model provider failed (Provider returned error). Try again."})]
    assert len(bodies) == 2 and client.persisted == []


def test_tool_call_written_as_text_is_run_not_shown(client, monkeypatch):
    leaked = ("<tool_call> <function=search_papers> <parameter=query> polar bear pollution </parameter> "
              "<parameter=limit> 10 </parameter> </function> </tool_call>")
    transport, bodies = scripted_provider([
        [chunk("<tool_"), chunk(leaked[6:]), "data: [DONE]"],
        [chunk("Found one."), "data: [DONE]"],
    ])
    use_provider(monkeypatch, transport)
    calls = []

    async def fake_tool(name, args, project_id):
        calls.append((name, args))
        return {"results": []}

    monkeypatch.setattr(nodes_router.paper_service, "call_tool", fake_tool)

    r = client.post(f"/nodes/{NODE}/messages", json={"content": "find a paper"})

    shown = "".join(d["text"] for name, d in events(r) if name == "token")
    assert shown == "Found one." and "tool_call" not in shown
    assert calls == [("search_papers", {"query": "polar bear pollution", "limit": 10})]
    assert client.persisted[0][3] == "Found one."
