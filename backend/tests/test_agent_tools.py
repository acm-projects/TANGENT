"""Agent tool suite: schema separation and dispatch (runs in CI, no secrets). The graph tools themselves are
exercised against the real DB in test_agent_tools_db.py."""
import asyncio
import os
import uuid

# app.database refuses to import without these; the engine connects lazily. Removed again so the real-DB test
# modules still skip themselves when no database is configured (same dance as test_nodes_messages.py).
_dummies = {"DATABASE_URL": "postgresql://dummy@localhost/dummy", "JWT_SECRET_KEY": "test-secret"}
_added = [k for k in _dummies if k not in os.environ]
os.environ.update({k: _dummies[k] for k in _added})

from app.agent import tools
from app.papers import service as paper_service
from app.routers import nodes_router

for _k in _added:
    del os.environ[_k]

P, U = uuid.uuid4(), uuid.uuid4()


def names(schemas):
    return [s["function"]["name"] for s in schemas]


def test_graph_tools_are_agent_only():
    graph = set(names(tools.GRAPH_TOOLS))
    assert graph == set(tools._HANDLERS)
    assert not graph & set(names(paper_service.TOOLS))
    assert set(names(paper_service.TOOLS)) <= set(names(tools.AGENT_TOOLS))
    assert nodes_router.paper_service.TOOLS is paper_service.TOOLS  # the node loop offers node tools only


def test_node_tools_fall_through_to_the_papers_service(monkeypatch):
    async def fake(name, args, project_id=None):
        return {"ran": name, "args": args, "project": project_id}

    monkeypatch.setattr(paper_service, "call_tool", fake)
    assert asyncio.run(tools.call_tool("search_papers", {"query": "q"}, P, U)) == \
        {"ran": "search_papers", "args": {"query": "q"}, "project": P}


def test_bad_calls_come_back_as_errors():
    run = lambda name, args: asyncio.run(tools.call_tool(name, args, P, U))
    assert "error" in run("get_node", ["not", "a", "dict"])
    assert "error" in run("get_node", {"wrong": 1})
    assert "error" in run("merge_nodes", {"node_ids": [str(uuid.uuid4())]})  # needs 2+
    assert "error" in run("merge_nodes", {"node_ids": "abc"})
    assert "error" in run("search_nodes", {"query": "  "})
    assert "error" in run("search_sources", {"query": ""})
    assert "error" in run("search_sources", {"query": "x", "source_ids": ["12"]})


def test_excerpt_centres_on_the_match():
    text = "a" * 300 + "needle" + "b" * 300
    out = tools._excerpt("NEEDLE", None, text)
    assert "needle" in out and len(out) <= tools.EXCERPT_CHARS + 2
    assert tools._excerpt("zzz", "title", "body") == ""
