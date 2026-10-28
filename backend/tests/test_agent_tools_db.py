"""Agent graph and source tools against the real DB (the LLM and Google are faked).
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
from app.main import app
from app.routers import nodes_router

sys.path.insert(0, os.path.dirname(__file__))
from test_tree_flow import _workspace_id, cleanup, fresh_pool, google, sign_up  # noqa: E402,F401  (fixtures)


def test_graph_tools_end_to_end(monkeypatch):
    async def fake_llm(messages, model, **_):
        yield {"text": "pong"}

    monkeypatch.setattr(nodes_router, "stream_openrouter", fake_llm)
    monkeypatch.setattr(tools, "stream_openrouter", fake_llm)

    with TestClient(app) as c:
        auth = sign_up(c)
        me = c.get("/auth/me", headers=auth).json()
        pid = c.post("/projects/", json={"project_name": "P", "workspace_id": _workspace_id(me["id"])},
                     headers=auth).json()["id"]
        root = c.get(f"/projects/{pid}/tree", headers=auth).json()["tree"]["root_node_id"]
        run = lambda name, project=pid, **args: asyncio.run(tools.call_tool(name, args, UUID(project), UUID(me["id"])))
        ask = lambda nid, q: c.post(f"/nodes/{nid}/messages", json={"content": q}, headers=auth)

        # branch: new children, original untouched
        a = run("branch_node", node_id=root, title="Alpha")
        b = run("branch_node", node_id=root)
        d = run("branch_node", node_id=root)
        assert (a["fork_index"], b["fork_index"]) == (1, 2) and a["parent_id"] == root and a["title"] == "Alpha"
        assert "error" in run("branch_node", node_id=str(uuid.uuid4()))
        listing = asyncio.run(tools.outline(UUID(pid), UUID(me["id"])))
        assert f"{a['node_id']} (parent {root}; empty; 0 branches): Alpha" in listing
        assert f"{root} (parent none, the root; empty; 3 branches)" in listing
        for n, q in ((a, "pingA"), (b, "pingB"), (d, "pingC")):
            ask(n["node_id"], q)

        # get: content, metadata, relationships; a node of another project is just not found
        got = run("get_node", node_id=a["node_id"])
        assert [m["content"] for m in got["messages"]] == ["pingA", "pong"]
        assert got["parent_id"] == root and got["child_ids"] == []
        assert run("get_node", node_id=root)["child_ids"] == [a["node_id"], b["node_id"], d["node_id"]]
        assert run("get_node", node_id=a["node_id"], project=str(uuid.uuid4()))["error"] == "Node not found"

        # search: match with branch context, wildcards are literal, no match is an empty list
        hit = run("search_nodes", query="pingA")["results"]
        assert [(h["node_id"], h["parent_id"]) for h in hit] == [(a["node_id"], root)] and "pingA" in hit[0]["excerpt"]
        assert run("search_nodes", query="ping_")["results"] == []
        assert len(run("search_nodes", query="ping", limit=2)["results"]) == 2
        assert run("search_nodes", query="no-such-text")["results"] == []

        # merge: 3 leaves, originals kept and linked; non-leaf and duplicate rejected
        assert "error" in run("merge_nodes", node_ids=[root, a["node_id"]])
        assert "error" in run("merge_nodes", node_ids=[a["node_id"], a["node_id"]])
        m = run("merge_nodes", node_ids=[a["node_id"], b["node_id"], d["node_id"]], title="All")
        assert m["parent_id"] == root
        merged = run("get_node", node_id=m["node_id"])
        assert merged["title"] == "All" and sorted(merged["merge_source_ids"]) == sorted([a["node_id"], b["node_id"], d["node_id"]])
        assert [x["branch_source"] for x in merged["messages"]] == ["a", "a", "b", "b", "c", "c"]
        assert len(run("get_node", node_id=a["node_id"])["messages"]) == 2
        assert run("get_node", node_id=a["node_id"])["merged_into_ids"] == [m["node_id"]]

        # delete: the subtree goes, the merge node stays and is reported as detached; the root stays
        child = run("branch_node", node_id=a["node_id"])
        gone = run("delete_node", node_id=a["node_id"])
        assert gone["ok"] and set(gone["deleted_node_ids"]) == {a["node_id"], child["node_id"]}
        assert gone["merge_nodes_detached"] == [m["node_id"]] and gone["parent_id"] == root
        assert "error" in run("get_node", node_id=child["node_id"])
        assert len(run("get_node", node_id=m["node_id"])["merge_source_ids"]) == 2
        assert "error" in run("delete_node", node_id=root)

        # ask_node: a leaf takes the message and keeps the exchange; a node with branches refuses
        x = run("branch_node", node_id=root)["node_id"]
        asked = run("ask_node", node_id=x, message="hello")
        assert asked["reply"] == "pong" and asked["node_id"] == x
        assert [m["content"] for m in run("get_node", node_id=x)["messages"]] == ["hello", "pong"]
        assert run("get_node", node_id=x)["title"] == "hello"
        assert "error" in run("ask_node", node_id=root, message="hi")
        assert "error" in run("ask_node", node_id=x, message="  ")

        # sources: none, then an upload still processing, then a ready one with an indexed passage
        assert run("search_sources", query="entropy")["passages"] == []
        paper = asyncio.run(_add_upload(pid, "processing"))
        out = run("search_sources", query="entropy")
        assert out["passages"] == [] and out["not_ready"] == [{"source_id": f"p{paper}", "status": "processing"}]
        assert "indexed yet" in out["message"]
        asyncio.run(_make_ready(paper))
        out = run("search_sources", query="entropy")
        assert [p["evidence_id"] for p in out["passages"]] == [f"p{paper}:c0"] and out["passages"][0]["pages"] == "3"
        assert "message" not in out
        assert run("search_sources", query="entropy", source_ids=[f"p{paper}"])["passages"]
        assert "error" in run("search_sources", query="entropy", source_ids=["p999999999"])
        assert "No passage matched" in run("search_sources", query="zebra")["message"]


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
