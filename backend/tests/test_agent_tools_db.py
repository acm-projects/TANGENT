"""Gent's tools and the nodes' source search against the real DB (the LLM and Google are faked).
Skipped without DATABASE_URL + JWT_SECRET_KEY (CI has no database). Cleans up its user afterwards."""
import asyncio
import os
import sys
import uuid
from uuid import UUID

import pytest
from dotenv import load_dotenv

load_dotenv()
if not (os.getenv("DATABASE_URL") and os.getenv("JWT_SECRET_KEY")):
    pytest.skip("needs DATABASE_URL and JWT_SECRET_KEY (a real database)", allow_module_level=True)

from fastapi.testclient import TestClient
from sqlalchemy import text

from app import database
from app.agent import tools
from app.core.openrouter import DEFAULT_MODEL_ID
from app.main import app
from app.routers import nodes_router

sys.path.insert(0, os.path.dirname(__file__))
from test_tree_flow import _workspace_id, cleanup, fresh_pool, google, sign_up  # noqa: E402,F401  (fixtures)


def test_gent_tools_end_to_end(monkeypatch):
    async def fake_llm(messages, model, **_):
        yield {"text": "pong"}

    monkeypatch.setattr(nodes_router, "stream_openrouter", fake_llm)

    with TestClient(app) as c:
        auth = sign_up(c)
        me = c.get("/auth/me", headers=auth).json()
        pid = c.post("/projects/", json={"project_name": "P", "workspace_id": _workspace_id(me["id"])},
                     headers=auth).json()["id"]
        root = c.get(f"/projects/{pid}/tree", headers=auth).json()["tree"]["root_node_id"]
        gent = tools.Run(project_id=UUID(pid), user_id=UUID(me["id"]), model=DEFAULT_MODEL_ID, cwd=UUID(root),
                         owner=True)
        run = lambda name, **args: asyncio.run(tools.call_tool(gent, name, args))
        chats = lambda nid: c.get(f"/nodes/{nid}", headers=auth).json()["chats"]

        # branch moves in; ask saves the exchange there, marked as Gent's
        a = run("branch", title="Alpha")["cwd"]
        assert a["address"] == "1.1" and a["title"] == "Alpha" and str(gent.cwd) == a["id"]
        asked = run("ask", question="pingA")
        assert asked["preview"] == "pong"
        assert [(m["content"], m.get("author")) for m in chats(a["id"])] == [("pingA", "gent"), ("pong", None)]
        run("cd", to="/")
        assert "has branches" in run("ask", question="hi")["error"]

        # bulk_ask: one branch per question, all answered and saved
        out = run("bulk_ask", questions=[{"question": "pingB"}, {"question": "pingC", "title": "Gamma"}])
        b, d = out["branches"]
        assert (b["address"], d["address"], d["title"]) == ("1.2", "1.3", "Gamma") and str(gent.cwd) == root
        assert [m["content"] for m in chats(d["id"])] == ["pingC", "pong"]

        # ls, cd and cat
        assert [x["address"] for x in run("ls")["branches"]] == ["1.1", "1.2", "1.3"]
        assert run("cd", to="1.2")["messages"] == 2
        assert "pingB" in run("cat")["content"]
        assert run("cd", to="..")["cwd"]["id"] == root

        # search: address and snippet; wildcards are literal
        hits = run("search", query="pingA")["results"]
        assert [(h["address"], h["id"]) for h in hits] == [("1.1", a["id"])] and "pingA" in hits[0]["snippet"]
        assert run("search", query="ping_")["results"] == []

        # merge moves into the joint node; rm takes a subtree (a merge hangs under its first source, so it goes too)
        # and moves Gent up
        m = run("merge", nodes=["1.1", "1.2", "1.3"], title="All")["cwd"]
        assert m["address"] == "J1" and m["title"] == "All"
        run("cd", to="1.1")
        child = run("branch")["cwd"]
        gone = run("rm", target="1.1")
        assert set(gone["deleted"]) == {"1.1", child["address"], "J1"} and gone["merges_detached"] == []
        assert gone["cwd"]["id"] == root
        assert "error" in run("rm", target="/")

        # another project's node is just not found
        assert "error" in run("cd", to=str(uuid.uuid4()))

        # sources are the nodes' tool now: none, then processing, then a ready passage
        call = lambda **args: asyncio.run(nodes_router.paper_service.call_tool("search_sources", args, UUID(pid)))
        assert call(query="entropy")["evidence"] == []
        paper = asyncio.run(_add_upload(pid, "processing"))
        out = call(query="entropy")
        assert out["evidence"] == [] and out["not_ready"] == [{"source_id": f"p{paper}", "status": "processing"}]
        asyncio.run(_make_ready(paper))
        out = call(query="entropy")
        assert [p["evidence_id"] for p in out["evidence"]] == [f"p{paper}:c0"] and out["evidence"][0]["pages"] == "3"
        assert "error" in call(query="entropy", source_ids=["p999999999"])
        assert "No passage matched" in call(query="zebra")["message"]


async def _add_upload(project_id: str, status: str) -> int:
    async with database.AsyncSessionLocal() as db:
        row = (await db.execute(text("""
            INSERT INTO papers (source, source_id, project_id, title, status)
            VALUES ('upload', :sid, :p, 'Test upload', :s) RETURNING id
        """), {"sid": f"{project_id}:{uuid.uuid4().hex}", "p": UUID(project_id), "s": status})).scalar_one()
        await db.commit()
        return row


async def _make_ready(paper_id: int) -> None:
    async with database.AsyncSessionLocal() as db:
        await db.execute(text("""
            INSERT INTO paper_chunks (paper_id, idx, section, page_start, page_end, text)
            VALUES (:id, 0, 'Intro', 3, 3, 'Entropy measures the uncertainty of a source.')
        """), {"id": paper_id})
        await db.execute(text("UPDATE papers SET status = 'ready' WHERE id = :id"), {"id": paper_id})
        await db.commit()


def test_gent_thread_is_kept_in_the_database():
    import json

    from app.agent import thread

    with TestClient(app) as c:
        auth = sign_up(c)
        me = c.get("/auth/me", headers=auth).json()
        pid = c.post("/projects/", json={"project_name": "T", "workspace_id": _workspace_id(me["id"])},
                     headers=auth).json()["id"]
        # the user's notes with no run going: stored with ids
        notes = c.post(f"/projects/{pid}/gent/notes", json={"notes": [{"id": None, "text": "Map it", "done": False}]},
                       headers=auth).json()["notes"]
        assert notes[0]["id"] == "n1"
        # a run's events, as its writer stores them
        run_id = uuid.uuid4()
        rows = [{"type": "task", "text": "go"}, {"type": "note", "turn": 1, "text": "Plan."},
                {"type": "reply", "turn": 1, "text": "Done."}]
        asyncio.run(thread.append(UUID(pid), UUID(me["id"]), run_id, rows, notes))

        # following the thread with no run going: everything stored, then the stream ends
        res = c.get(f"/projects/{pid}/gent", headers=auth)
        frame = res.text.split("\n")
        assert frame[0] == "event: thread"
        body = json.loads(frame[1].removeprefix("data: "))
        assert body["events"] == rows and body["notes"] == notes and body["live"] is False

        assert c.delete(f"/projects/{pid}/gent", headers=auth).status_code == 204
        body = json.loads(c.get(f"/projects/{pid}/gent", headers=auth).text.split("\n")[1].removeprefix("data: "))
        assert body == {"events": [], "notes": [], "live": False}
