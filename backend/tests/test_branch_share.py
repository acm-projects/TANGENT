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

        assert len(c.get(f"/projects/{pid}/tree", headers=owner).json()["nodes"]) == 4  # owner sees everything

        # writes on hidden nodes are refused outright, before anything is copied
        assert c.post(f"/nodes/{a1}/fork", headers=sharee).status_code == 404
        r = c.post(f"/nodes/{b}/messages", json={"content": "x"}, headers=sharee)  # streams: refusal is an SSE error
        assert "event: error" in r.text and "event: token" not in r.text and "fork" not in r.text
        assert c.post("/nodes/merge", json={"source_leaf_ids": [a1, b]}, headers=sharee).status_code == 404

        # a write on a visible node forks the project, but the copy holds only root -> a (+ the new child)
        r = c.post(f"/nodes/{a}/fork", headers=sharee)
        assert r.status_code == 200
        fork = r.json()["fork"]
        assert set(fork["node_map"]) == {root, a}
        copy = c.get(f"/projects/{fork['project_id']}/tree", headers=sharee).json()
        assert len(copy["nodes"]) == 3


def project_with_branches(c):
    """Owner + sharee signed up; a project with root -> a, root -> b."""
    owner = sign_up(c, OWNER)
    sharee = sign_up(c, SHAREE)
    wid, slug = workspace_of(c.get("/auth/me", headers=owner).json()["id"])
    pid = c.post("/projects/", json={"project_name": "P", "workspace_id": wid}, headers=owner).json()["id"]
    root = c.get(f"/projects/{pid}/tree", headers=owner).json()["tree"]["root_node_id"]
    a = c.post(f"/nodes/{root}/fork", headers=owner).json()["id"]
    b = c.post(f"/nodes/{root}/fork", headers=owner).json()["id"]
    return owner, sharee, f"/shares/{slug}/{pid}", pid, root, a, b


def test_whole_project_share_allows_a_branch_invite(sent):
    """A whole-project share no longer blocks a branch invite (create, resend, accept); the user then
    holds both rows and resolves to full access. A duplicate whole-project share is still refused."""
    with TestClient(app) as c:
        owner, sharee, base, pid, root, a, b = project_with_branches(c)

        assert c.post(f"{base}/share", json={"email": SHAREE}, headers=owner).status_code == 201
        assert c.post(f"/shares/{sent[SHAREE]}/accept", headers=sharee).status_code == 200
        assert len(c.get(f"/projects/{pid}/tree", headers=sharee).json()["nodes"]) == 3

        # still refused: the whole project, twice
        assert c.post(f"{base}/share", json={"email": SHAREE}, headers=owner).status_code == 400

        # create: allowed, and listed under the branch only
        assert c.post(f"{base}/share", json={"email": SHAREE, "branch_node_id": a}, headers=owner).status_code == 201
        invite = c.get(f"{base}/shares", params={"branch_node_id": a}, headers=owner).json()["shares"]
        assert [i["type"] for i in invite] == ["invitation"]

        # resend: allowed too, and issues a fresh token
        old_token = sent[SHAREE]
        assert c.post(f"{base}/invitations/{invite[0]['id']}/resend", headers=owner).status_code == 200
        assert sent[SHAREE] != old_token

        # accept: allowed; full access is unchanged, the sharee did not get narrowed to the branch
        assert c.post(f"/shares/{sent[SHAREE]}/accept", headers=sharee).status_code == 200
        t = c.get(f"/projects/{pid}/tree", headers=sharee).json()
        assert {n["id"] for n in t["nodes"]} == {root, a, b}
        assert c.get(f"/nodes/{b}", headers=sharee).status_code == 200


def test_a_second_branch_share_is_still_refused(sent):
    """Branch shares stay one per user per project (branch_scope.branch_root assumes it)."""
    with TestClient(app) as c:
        owner, sharee, base, pid, root, a, b = project_with_branches(c)

        # two pending branch invites to different branches can coexist...
        assert c.post(f"{base}/share", json={"email": SHAREE, "branch_node_id": a}, headers=owner).status_code == 201
        token_a = sent[SHAREE]
        assert c.post(f"{base}/share", json={"email": SHAREE, "branch_node_id": b}, headers=owner).status_code == 201
        token_b = sent[SHAREE]

        # ...but only the first can be accepted
        assert c.post(f"/shares/{token_a}/accept", headers=sharee).status_code == 200
        assert c.post(f"/shares/{token_b}/accept", headers=sharee).status_code == 400

        # and with an active branch share, a new branch invite is refused up front
        assert c.post(f"{base}/share", json={"email": SHAREE, "branch_node_id": b}, headers=owner).status_code == 400
        assert {n["id"] for n in c.get(f"/projects/{pid}/tree", headers=sharee).json()["nodes"]} == {root, a}


def test_sharing_a_merge_includes_both_parent_paths_and_project_copy(sent):
    with TestClient(app) as c:
        owner, sharee, base, pid, root, a, b = project_with_branches(c)
        sibling = c.post(f"/nodes/{root}/fork", headers=owner).json()["id"]
        merged = c.post("/nodes/merge", json={"source_leaf_ids": [a, b]}, headers=owner).json()
        merge_id = merged["id"]

        assert c.post(f"{base}/share", json={"email": SHAREE, "branch_node_id": merge_id},
                      headers=owner).status_code == 201
        assert c.post(f"/shares/{sent[SHAREE]}/accept", headers=sharee).status_code == 200
        visible = c.get(f"/projects/{pid}/tree", headers=sharee).json()["nodes"]
        assert {node["id"] for node in visible} == {root, a, b, merge_id}
        assert sibling not in {node["id"] for node in visible}
        assert next(node for node in visible if node["id"] == merge_id)["merge_source_ids"] == [a, b]

        fork = c.post(f"/nodes/{merge_id}/fork", headers=sharee).json()["fork"]
        assert set(fork["node_map"]) == {root, a, b, merge_id}
        copied = c.get(f"/projects/{fork['project_id']}/tree", headers=sharee).json()["nodes"]
        assert len(copied) == 5
