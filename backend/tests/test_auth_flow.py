"""End-to-end login/signup flow against the real DB. Only Google's token exchange is faked.
Needs DATABASE_URL (+ DB_USER/DB_PASSWORD) and JWT_SECRET_KEY in the environment/.env."""
import asyncio
import uuid
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.database import DATABASE_URL, _local
from app.main import app
from app.routers import auth_router

EMAIL = f"tangent-test-{uuid.uuid4().hex[:8]}@example.com"
INVITE = "/invite/" + "a" * 20


@pytest.fixture
def google(monkeypatch):
    async def exchange(code, verifier, *a):
        return {"id_token": "fake"}

    async def verify(_):
        return {"email": EMAIL, "sub": "g-" + EMAIL, "name": "Test User", "picture": None}

    monkeypatch.setattr(auth_router, "exchange_google_code_for_tokens", exchange)
    monkeypatch.setattr(auth_router, "verify_google_id_token", verify)


@pytest.fixture(autouse=True)
def cleanup():
    yield

    async def run():
        eng = create_async_engine(DATABASE_URL, poolclass=NullPool,
                                  connect_args={"statement_cache_size": 0, **({} if _local else {"ssl": "require"})})
        async with eng.begin() as c:
            uid = (await c.execute(text("select id from users where email=:e"), {"e": EMAIL})).scalar()
            if uid:
                await c.execute(text("delete from sessions where user_id=:u"), {"u": uid})
                await c.execute(text("delete from workspaces where owner_id=:u"), {"u": uid})
                await c.execute(text("delete from users where id=:u"), {"u": uid})
        await eng.dispose()

    asyncio.run(run())


def google_login(c, next_path=None):
    r = c.get("/auth/login/google", params={"next": next_path} if next_path else None, follow_redirects=False)
    assert r.status_code in (302, 307) and "accounts.google.com" in r.headers["location"]
    state = parse_qs(urlparse(r.headers["location"]).query)["state"][0]
    return c.get("/auth/callback/google", params={"state": state, "code": "x"}, follow_redirects=False)


def test_signup_to_logout_flow(google):
    with TestClient(app) as c:
        # --- signup: new user lands on /onboarding with a token
        r = google_login(c, INVITE)
        assert r.status_code in (302, 307), r.text
        u = urlparse(r.headers["location"])
        q = parse_qs(u.query)
        assert u.path == "/onboarding" and q["next"] == [INVITE]
        token = q["access_token"][0]
        assert "refresh_token" in c.cookies
        auth = {"Authorization": f"Bearer {token}"}

        me = c.get("/auth/me", headers=auth).json()
        assert me["email"] == EMAIL and me["onboarding_completed"] is False
        assert c.get("/auth/me").status_code in (401, 403)

        # --- onboarding: unsafe next is ignored, workspace is created, can't repeat
        r = c.post("/auth/onboarding", json={"workspace_name": "My Test WS!", "next": "https://evil.com"}, headers=auth)
        assert r.status_code == 201, r.text
        slug = r.json()["redirect"].lstrip("/")
        assert slug.startswith("my-test-ws") and "evil" not in r.json()["redirect"]
        assert c.post("/auth/onboarding", json={"workspace_name": "again"}, headers=auth).status_code == 400
        assert c.get("/auth/me", headers=auth).json()["onboarding_completed"] is True

        # --- returning login goes straight to the workspace
        r = google_login(c)
        u = urlparse(r.headers["location"])
        assert u.path == f"/{slug}" and "access_token" in parse_qs(u.query)

        # --- refresh rotates the cookie and returns a usable access token
        old = c.cookies["refresh_token"]
        r = c.post("/auth/refresh")
        assert r.status_code == 200, r.text
        assert c.get("/auth/me", headers={"Authorization": f"Bearer {r.json()['access_token']}"}).status_code == 200
        assert c.cookies["refresh_token"] != old

        # --- logout kills the session
        assert c.post("/auth/logout").status_code == 200
        assert c.post("/auth/refresh").status_code == 401


def test_callback_rejects_bad_state_and_missing_verifier(google):
    with TestClient(app) as c:
        c.get("/auth/login/google", follow_redirects=False)
        assert c.get("/auth/callback/google", params={"state": "wrong", "code": "x"}).status_code == 400
    with TestClient(app) as c:  # no cookies at all
        assert c.get("/auth/callback/google", params={"state": "s", "code": "x"}).status_code == 400
