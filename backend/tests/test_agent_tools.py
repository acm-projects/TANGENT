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


def test_ask_node_prompts_the_leaf_and_saves_the_exchange(monkeypatch):
    from contextlib import asynccontextmanager
    from types import SimpleNamespace

    node, saved, sent = uuid.uuid4(), [], []

    @asynccontextmanager
    async def session(user_id):
        yield object()

    async def find(db, node_id, project_id, user_id):
        return SimpleNamespace(id=node, model=None)

    async def owner(db, project_id, user_id):
        return None

    async def path(db, node_id, user_id):
        return [nodes_router.PathNode(id="root", chats=[])], P

    async def stream(messages, model):
        sent.append((messages, model))
        yield {"text": "an "}
        yield {"text": "answer"}
        yield {"usage": {"total_tokens": 7}, "model": model}

    async def persist(*args):
        saved.append(args)

    monkeypatch.setattr(tools, "_session", session)
    monkeypatch.setattr(tools, "_node", find)
    monkeypatch.setattr(tools, "_require_owner", owner)
    monkeypatch.setattr(nodes_router, "_load_path", path)
    monkeypatch.setattr(nodes_router, "_persist", persist)
    monkeypatch.setattr(tools, "stream_openrouter", stream)

    out = asyncio.run(tools.call_tool("ask_node", {"node_id": str(node), "message": " hi "}, P, U, model=tools.DEFAULT_MODEL_ID))
    assert out == {"node_id": str(node), "model": tools.DEFAULT_MODEL_ID, "reply": "an answer"}
    assert sent[0][0][-1] == {"role": "user", "content": "hi"} and sent[0][1] == tools.DEFAULT_MODEL_ID
    assert saved == [(U, node, "hi", "an answer", tools.DEFAULT_MODEL_ID, 7)]
    assert "error" in asyncio.run(tools.call_tool("ask_node", {"node_id": str(node), "message": " "}, P, U))


def test_write_node_saves_the_agents_own_text_as_a_child(monkeypatch):
    from contextlib import asynccontextmanager
    from types import SimpleNamespace

    parent, created = uuid.uuid4(), []

    class Db:
        async def commit(self):
            pass

    @asynccontextmanager
    async def session(user_id):
        yield Db()

    async def find(db, node_id, project_id, user_id):
        return SimpleNamespace(id=parent, tree_id=uuid.uuid4())

    async def owner(db, project_id, user_id):
        return None

    async def create_child(db, **kw):
        created.append(kw)
        return SimpleNamespace(id=uuid.uuid4(), fork_index=1, title=None)

    monkeypatch.setattr(tools, "_session", session)
    monkeypatch.setattr(tools, "_node", find)
    monkeypatch.setattr(tools, "_require_owner", owner)
    monkeypatch.setattr(nodes_router, "_create_child", create_child)

    out = asyncio.run(tools.call_tool("write_node", {"parent_id": str(parent), "title": " Finding ", "body": " Text [p1:c2] "}, P, U))
    assert out["title"] == "Finding" and out["parent_id"] == str(parent)
    chats = created[0]["chats"]
    assert [(m["role"], m["content"], m["seq"]) for m in chats] == [("user", "Finding", 0), ("assistant", "Text [p1:c2]", 1)]
    for bad in ({"title": " ", "body": "x"}, {"title": "t", "body": " "}, {"title": "t", "body": "x" * 20_001}):
        assert "error" in asyncio.run(tools.call_tool("write_node", {"parent_id": str(parent), **bad}, P, U))
    assert len(created) == 1
