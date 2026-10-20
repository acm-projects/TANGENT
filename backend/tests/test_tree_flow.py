"""Project -> tree -> fork -> prompt flow against the real DB. Only Google and the LLM are faked.
Skipped without DATABASE_URL + JWT_SECRET_KEY (CI has no database). Cleans up its user afterwards."""
import asyncio
import os
import uuid
from urllib.parse import parse_qs, urlparse

import pytest
from dotenv import load_dotenv

load_dotenv()
if not (os.getenv("DATABASE_URL") and os.getenv("JWT_SECRET_KEY")):
    pytest.skip("needs DATABASE_URL and JWT_SECRET_KEY (a real database)", allow_module_level=True)

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app import database
from app.database import DATABASE_URL, _local
from app.main import app
from app.routers import auth_router, nodes_router

EMAIL = f"tangent-tree-test-{uuid.uuid4().hex[:8]}@example.com"


@pytest.fixture(autouse=True)
def google(monkeypatch):
    async def exchange(code, verifier, *a):
        return {"id_token": "fake"}

    async def verify(_):
        return {"email": EMAIL, "sub": "g-" + EMAIL, "name": "Tree Test", "picture": None}

    monkeypatch.setattr(auth_router, "exchange_google_code_for_tokens", exchange)
    monkeypatch.setattr(auth_router, "verify_google_id_token", verify)


@pytest.fixture(autouse=True)
def fresh_pool(monkeypatch):
    """The app's pooled connections belong to the event loop of whichever test used them first;
    TestClient makes a new loop per test, so give this one unpooled sessions."""
    engine = create_async_engine(DATABASE_URL, poolclass=NullPool,
                                 connect_args={"statement_cache_size": 0, **({} if _local else {"ssl": "require"})})
    sessions = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False, autoflush=False)
    monkeypatch.setattr(database, "AsyncSessionLocal", sessions)
    monkeypatch.setattr(nodes_router, "AsyncSessionLocal", sessions)


@pytest.fixture(autouse=True)
def cleanup():
    yield

    async def run():
        eng = create_async_engine(DATABASE_URL, poolclass=NullPool,
                                  connect_args={"statement_cache_size": 0, **({} if _local else {"ssl": "require"})})
        async with eng.begin() as c:
            uid = (await c.execute(text("select id from users where email=:e"), {"e": EMAIL})).scalar()
            if uid:  # workspaces -> projects -> trees/nodes cascade
                await c.execute(text("delete from sessions where user_id=:u"), {"u": uid})
                await c.execute(text("delete from workspaces where owner_id=:u"), {"u": uid})
                await c.execute(text("delete from users where id=:u"), {"u": uid})
        await eng.dispose()

    asyncio.run(run())


def sign_up(c):
    state = parse_qs(urlparse(c.get("/auth/login/google", follow_redirects=False).headers["location"]).query)["state"][0]
    r = c.get("/auth/callback/google", params={"state": state, "code": "x"}, follow_redirects=False)
    auth = {"Authorization": "Bearer " + parse_qs(urlparse(r.headers["location"]).query)["access_token"][0]}
    assert c.post("/auth/onboarding", json={"workspace_name": "Tree WS"}, headers=auth).status_code == 201
    return auth


def test_tree_fork_and_prompt(monkeypatch):
    async def fake_llm(messages, model):
        seen.append(messages)
        yield {"text": "pong"}

    seen = []
    monkeypatch.setattr(nodes_router, "stream_openrouter", fake_llm)

    with TestClient(app) as c:
        auth = sign_up(c)
        me = c.get("/auth/me", headers=auth).json()
        project = c.post("/projects/", json={"project_name": "P", "workspace_id": _workspace_id(me["id"])},
                         headers=auth).json()
        pid = project["id"]

        # first visit creates the tree with one empty root; the second returns the same one
        t = c.get(f"/projects/{pid}/tree", headers=auth).json()
        assert len(t["nodes"]) == 1 and t["tree"]["root_node_id"] == t["nodes"][0]["id"]
        assert c.get(f"/projects/{pid}/tree", headers=auth).json()["tree"]["id"] == t["tree"]["id"]
        root = t["tree"]["root_node_id"]
        assert c.get(f"/nodes/{root}", headers=auth).json()["chats"] == []

        # forks get 1, 2, ...; a node with children refuses prompts
        a = c.post(f"/nodes/{root}/fork", headers=auth).json()
        b = c.post(f"/nodes/{root}/fork", headers=auth).json()
        assert (a["fork_index"], b["fork_index"]) == (1, 2) and a["parent_id"] == root
        assert len(c.get(f"/trees/{t['tree']['id']}", headers=auth).json()["nodes"]) == 3
        assert c.post(f"/nodes/{root}/messages", json={"content": "x"}, headers=auth).status_code == 409

        # a leaf takes a prompt, the reply streams, and both messages are saved
        r = c.post(f"/nodes/{a['id']}/messages", json={"content": "ping"}, headers=auth)
        assert "event: token" in r.text and "event: done" in r.text
        node = c.get(f"/nodes/{a['id']}", headers=auth).json()
        assert [(m["role"], m["content"], m["seq"]) for m in node["chats"]] == [("user", "ping", 0), ("assistant", "pong", 1)]
        assert node["title"] == "ping"
        assert node["model"] == nodes_router.DEFAULT_MODEL_ID
        assert node["tokens"] == 0
        tree_node = next(n for n in c.get(f"/trees/{t['tree']['id']}", headers=auth).json()["nodes"] if n["id"] == a["id"])
        assert tree_node["model"] == node["model"]
        assert tree_node["tokens"] == node["tokens"]

        # deleting a branch takes its children with it; the root can't be deleted
        a2 = c.post(f"/nodes/{a['id']}/fork", headers=auth).json()
        assert c.delete(f"/nodes/{a['id']}", headers=auth).status_code == 204
        assert c.get(f"/nodes/{a2['id']}", headers=auth).status_code == 404
        assert len(c.get(f"/trees/{t['tree']['id']}", headers=auth).json()["nodes"]) == 2
        assert c.delete(f"/nodes/{root}", headers=auth).status_code == 409

        # unauthenticated callers get nothing
        assert c.get(f"/nodes/{a['id']}").status_code in (401, 403)


def test_simultaneous_first_visits_make_one_tree():
    from concurrent.futures import ThreadPoolExecutor

    with TestClient(app) as c:
        auth = sign_up(c)
        me = c.get("/auth/me", headers=auth).json()
        pid = c.post("/projects/", json={"project_name": "P", "workspace_id": _workspace_id(me["id"])},
                     headers=auth).json()["id"]

        with ThreadPoolExecutor(4) as pool:
            trees = list(pool.map(lambda _: c.get(f"/projects/{pid}/tree", headers=auth).json(), range(4)))

        assert len({t["tree"]["id"] for t in trees}) == 1 and all(len(t["nodes"]) == 1 for t in trees)


def test_simultaneous_forks_get_distinct_indexes():
    from concurrent.futures import ThreadPoolExecutor

    with TestClient(app) as c:
        auth = sign_up(c)
        me = c.get("/auth/me", headers=auth).json()
        pid = c.post("/projects/", json={"project_name": "P", "workspace_id": _workspace_id(me["id"])},
                     headers=auth).json()["id"]
        root = c.get(f"/projects/{pid}/tree", headers=auth).json()["tree"]["root_node_id"]

        # 3 racers, 3 attempts each: a loser can lose at most twice, so every request must succeed
        with ThreadPoolExecutor(3) as pool:
            rs = list(pool.map(lambda _: c.post(f"/nodes/{root}/fork", headers=auth), range(3)))

        assert [r.status_code for r in rs] == [200, 200, 200]
        assert sorted(r.json()["fork_index"] for r in rs) == [1, 2, 3]


def _workspace_id(user_id):
    """The API doesn't expose workspace ids, so read it straight from the table."""
    async def run():
        eng = create_async_engine(DATABASE_URL, poolclass=NullPool,
                                  connect_args={"statement_cache_size": 0, **({} if _local else {"ssl": "require"})})
        async with eng.connect() as c:
            wid = (await c.execute(text("select id from workspaces where owner_id=:u"), {"u": user_id})).scalar()
        await eng.dispose()
        return str(wid)

    return asyncio.run(run())
