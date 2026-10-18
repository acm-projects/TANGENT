"""Branch-only sharing against the real DB: a sharee invited to one node sees only the path from the
root down to that node. Only Google and the invite email are faked. Skipped without DATABASE_URL + JWT_SECRET_KEY.
Cleans up both users afterwards."""
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
from app.routers import auth_router, nodes_router, shares_router

TAG = uuid.uuid4().hex[:8]
OWNER = f"tangent-branch-owner-{TAG}@example.com"
SHAREE = f"tangent-branch-sharee-{TAG}@example.com"
signing_in = {"email": OWNER}
CONNECT = {"statement_cache_size": 0, **({} if _local else {"ssl": "require"})}


@pytest.fixture(autouse=True)
def google(monkeypatch):
    async def exchange(code, verifier, *a):
        return {"id_token": "fake"}

    async def verify(_):
        e = signing_in["email"]
        return {"email": e, "sub": "g-" + e, "name": e.split("@")[0], "picture": None}

    monkeypatch.setattr(auth_router, "exchange_google_code_for_tokens", exchange)
    monkeypatch.setattr(auth_router, "verify_google_id_token", verify)


@pytest.fixture(autouse=True)
def fresh_pool(monkeypatch):
    engine = create_async_engine(DATABASE_URL, poolclass=NullPool, connect_args=CONNECT)
    sessions = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False, autoflush=False)
    monkeypatch.setattr(database, "AsyncSessionLocal", sessions)
    monkeypatch.setattr(nodes_router, "AsyncSessionLocal", sessions)


@pytest.fixture(autouse=True)
def cleanup():
    yield

    async def run():
        eng = create_async_engine(DATABASE_URL, poolclass=NullPool, connect_args=CONNECT)
        async with eng.begin() as c:
            for email in (OWNER, SHAREE):
                uid = (await c.execute(text("select id from users where email=:e"), {"e": email})).scalar()
                if uid:
                    await c.execute(text("delete from sessions where user_id=:u"), {"u": uid})
                    await c.execute(text("delete from workspaces where owner_id=:u"), {"u": uid})
                    await c.execute(text("delete from users where id=:u"), {"u": uid})
        await eng.dispose()

    asyncio.run(run())


@pytest.fixture
def sent(monkeypatch):
    """Invite emails by recipient -> raw token, instead of really sending."""
    tokens = {}

    def fake_send(to_email, token, project_name, inviter_name):
        tokens[to_email] = token
        return True

    monkeypatch.setattr(shares_router, "send_invite_email", fake_send)
    return tokens


def sign_up(c, email):
    signing_in["email"] = email
    state = parse_qs(urlparse(c.get("/auth/login/google", follow_redirects=False).headers["location"]).query)["state"][0]
    r = c.get("/auth/callback/google", params={"state": state, "code": "x"}, follow_redirects=False)
    auth = {"Authorization": "Bearer " + parse_qs(urlparse(r.headers["location"]).query)["access_token"][0]}
    assert c.post("/auth/onboarding", json={"workspace_name": "Branch WS"}, headers=auth).status_code == 201
    return auth


def workspace_of(user_id):
    async def run():
        eng = create_async_engine(DATABASE_URL, poolclass=NullPool, connect_args=CONNECT)
        async with eng.connect() as c:
            row = (await c.execute(text("select id, slug from workspaces where owner_id=:u"), {"u": user_id})).one()
        await eng.dispose()
        return str(row.id), row.slug

    return asyncio.run(run())


def test_branch_sharee_sees_only_the_branch(sent):
    with TestClient(app) as c:
        owner = sign_up(c, OWNER)
        sharee = sign_up(c, SHAREE)

        wid, slug = workspace_of(c.get("/auth/me", headers=owner).json()["id"])
        pid = c.post("/projects/", json={"project_name": "P", "workspace_id": wid}, headers=owner).json()["id"]
        root = c.get(f"/projects/{pid}/tree", headers=owner).json()["tree"]["root_node_id"]
        a = c.post(f"/nodes/{root}/fork", headers=owner).json()["id"]
        b = c.post(f"/nodes/{root}/fork", headers=owner).json()["id"]
        a1 = c.post(f"/nodes/{a}/fork", headers=owner).json()["id"]

        base = f"/shares/{slug}/{pid}"

        # only a node of this project can be shared
        assert c.post(f"{base}/share", json={"email": SHAREE, "branch_node_id": str(uuid.uuid4())},
                      headers=owner).status_code == 404

        assert c.post(f"{base}/share", json={"email": SHAREE, "branch_node_id": a}, headers=owner).status_code == 201
        # the same branch can't be invited twice, but listing is per branch
        assert c.post(f"{base}/share", json={"email": SHAREE, "branch_node_id": a}, headers=owner).status_code == 400
        assert len(c.get(f"{base}/shares", params={"branch_node_id": a}, headers=owner).json()["shares"]) == 1
        assert c.get(f"{base}/shares", headers=owner).json()["shares"] == []  # project panel: not listed

        assert c.post(f"/shares/{sent[SHAREE]}/accept", headers=sharee).status_code == 200

        # the sharee's tree is root -> a: the real root stays, sibling `b` and the child `a1` are hidden
        t = c.get(f"/projects/{pid}/tree", headers=sharee).json()
        assert {n["id"] for n in t["nodes"]} == {root, a}
        assert t["tree"]["root_node_id"] == root
        assert next(n for n in t["nodes"] if n["id"] == a)["parent_id"] == root
        assert {n["id"] for n in c.get(f"/trees/{t['tree']['id']}", headers=sharee).json()["nodes"]} == {root, a}

        assert c.get(f"/nodes/{root}", headers=sharee).status_code == 200
        assert c.get(f"/nodes/{a}", headers=sharee).status_code == 200
        assert c.get(f"/nodes/{a1}", headers=sharee).status_code == 404
        assert c.get(f"/nodes/{b}", headers=sharee).status_code == 404

        # the owner still sees everything, and the sharee still can't write
        assert len(c.get(f"/projects/{pid}/tree", headers=owner).json()["nodes"]) == 4
        assert c.post(f"/nodes/{a1}/fork", headers=sharee).status_code in (403, 404)


def test_whole_project_share_still_sees_everything(sent):
    with TestClient(app) as c:
        owner = sign_up(c, OWNER)
        sharee = sign_up(c, SHAREE)

        wid, slug = workspace_of(c.get("/auth/me", headers=owner).json()["id"])
        pid = c.post("/projects/", json={"project_name": "P", "workspace_id": wid}, headers=owner).json()["id"]
        root = c.get(f"/projects/{pid}/tree", headers=owner).json()["tree"]["root_node_id"]
        c.post(f"/nodes/{root}/fork", headers=owner)

        assert c.post(f"/shares/{slug}/{pid}/share", json={"email": SHAREE}, headers=owner).status_code == 201
        assert c.post(f"/shares/{sent[SHAREE]}/accept", headers=sharee).status_code == 200

        t = c.get(f"/projects/{pid}/tree", headers=sharee).json()
        assert len(t["nodes"]) == 2 and t["tree"]["root_node_id"] == root
        # a full share already covers any branch
        a = t["nodes"][1]["id"] if t["nodes"][0]["id"] == root else t["nodes"][0]["id"]
        assert c.post(f"/shares/{slug}/{pid}/share", json={"email": SHAREE, "branch_node_id": a},
                      headers=owner).status_code == 400
