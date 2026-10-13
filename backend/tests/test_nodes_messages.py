"""POST /nodes/:id/messages with the provider and the database faked (runs in CI, no secrets)."""
import json
import os
import uuid
from types import SimpleNamespace

import httpx
import pytest

# app.database refuses to import without these; the engine connects lazily, so dummies are enough.
os.environ.setdefault("DATABASE_URL", "postgresql://dummy@localhost/dummy")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret")

from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.auth import get_current_user
from app.context.schemas import PathNode
from app.core import openrouter
from app.database import get_db_session
from app.main import app
from app.routers import nodes_router

NODE = uuid.uuid4()
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


@pytest.fixture
def client(monkeypatch):
    persisted = []

    async def no_db():
        yield None

    async def fake_persist(user_id, node_id, user_text, assistant_text):
        persisted.append((user_id, node_id, user_text, assistant_text))

    async def fake_path(db, node_id, user_id):
        return [PathNode(id="root", chats=[
            {"role": "user", "content": "earlier q", "seq": 0, "created_at": "2026-01-01T00:00:00Z"},
            {"role": "assistant", "content": "earlier a", "seq": 1, "created_at": "2026-01-01T00:00:01Z"},
        ])]

    app.dependency_overrides[get_current_user] = lambda: USER
    app.dependency_overrides[get_db_session] = no_db
    monkeypatch.setattr(nodes_router, "_persist", fake_persist)
    monkeypatch.setattr(nodes_router, "_load_path", fake_path)
    c = TestClient(app)
    c.persisted = persisted
    yield c
    app.dependency_overrides.clear()


def use_provider(monkeypatch, transport):
    real = openrouter.stream_openrouter
    monkeypatch.setattr(
        nodes_router, "stream_openrouter", lambda msgs, model: real(msgs, model, transport=transport)
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
    assert [m["content"] for m in seen["body"]["messages"]] == ["earlier q", "earlier a", "hi"]
    assert client.persisted == [(USER.id, NODE, "hi", "Hello")]


def test_provider_error_is_an_error_event_and_saves_nothing(client, monkeypatch):
    transport, _ = provider(["rate limited"], status=429)
    use_provider(monkeypatch, transport)

    r = client.post(f"/nodes/{NODE}/messages", json={"content": "hi"})

    assert events(r) == [("error", {"message": "rate limited\n\n"})]
    assert client.persisted == []


def test_unknown_model_is_400(client):
    r = client.post(f"/nodes/{NODE}/messages", json={"content": "hi", "model": "nope"})
    assert r.status_code == 400


def test_requires_auth():
    r = TestClient(app).post(f"/nodes/{NODE}/messages", json={"content": "hi"})
    assert r.status_code in (401, 403)


class FakeDb:
    """Stands in for the session: first execute() is the path query, second the has_child/is_owner flags."""

    def __init__(self, path_rows, has_child=False, is_owner=True):
        flags = SimpleNamespace(has_child=has_child, is_owner=is_owner)
        self.results = [SimpleNamespace(all=lambda: path_rows), SimpleNamespace(one=lambda: flags)]

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
async def test_load_path_403_for_sharee():
    with pytest.raises(HTTPException) as e:
        await load(FakeDb([SimpleNamespace(id="a", chats=[])], is_owner=False))
    assert e.value.status_code == 403


@pytest.fixture
def anyio_backend():
    return "asyncio"
