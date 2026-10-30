"""POST /projects/:id/agent with the model, the tools and the database faked (runs in CI, no secrets)."""
import json
import os
import uuid
from types import SimpleNamespace

import pytest

# app.database refuses to import without these; removed again after (see test_nodes_messages.py)
_dummies = {"DATABASE_URL": "postgresql://dummy@localhost/dummy", "JWT_SECRET_KEY": "test-secret"}
_added = [k for k in _dummies if k not in os.environ]
os.environ.update({k: _dummies[k] for k in _added})

from fastapi.testclient import TestClient

from app.agent import router as agent_router
from app.auth import get_current_user
from app.database import get_db_session
from app.main import app

for _k in _added:
    del os.environ[_k]

PROJECT = uuid.uuid4()
USER = SimpleNamespace(id=uuid.uuid4())
NODE = str(uuid.uuid4())


def tool_call(id, name, args):
    return {"tool_calls": [{"id": id, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}]}


@pytest.fixture
def agent(monkeypatch):
    requests, ran = [], []
    script = []  # one list of stream events per model turn

    class NoDb:
        async def rollback(self):
            pass

    async def no_db():
        yield NoDb()

    async def fake_stream(messages, model, transport=None, tools=None, tool_choice=None):
        requests.append({"messages": [dict(m) for m in messages], "tools": tools, "tool_choice": tool_choice})
        for event in script.pop(0):
            yield event

    async def fake_call(name, args, project_id, user_id, model=None):
        ran.append((name, args, project_id, user_id, model))
        return {"node_id": "new"} if name in ("branch_node", "write_node") else {"error": "boom"}

    async def fake_access(db, project_id, user):
        return None, "owner"

    async def fake_outline(project_id, user_id, limit=100):
        return f"- {NODE} (parent none, the root): Root"

    app.dependency_overrides[get_current_user] = lambda: USER
    app.dependency_overrides[get_db_session] = no_db
    monkeypatch.setattr(agent_router, "stream_openrouter", fake_stream)
    monkeypatch.setattr(agent_router.tools, "call_tool", fake_call)
    monkeypatch.setattr(agent_router.tools, "outline", fake_outline)
    monkeypatch.setattr(agent_router, "get_project_with_role", fake_access)
    with TestClient(app) as c:
        yield c, script, requests, ran
    app.dependency_overrides.clear()


def ask(c, content="Add a branch to Root", **extra):
    return c.post(f"/projects/{PROJECT}/agent", json={"messages": [{"role": "user", "content": content}], **extra})


def test_tool_loop_runs_calls_then_answers(agent):
    c, script, requests, ran = agent
    script += [
        [tool_call("1", "branch_node", {"node_id": NODE, "title": "T"})],
        [tool_call("2", "delete_node", {"node_id": "new"})],
        [{"text": "Added a branch, then it failed to delete."}],
    ]
    r = ask(c, active_node_id=NODE)
    assert r.status_code == 200
    body = r.json()
    assert body["reply"] == "Added a branch, then it failed to delete."
    assert [(t["name"], t["result"]) for t in body["tool_calls"]] == [
        ("branch_node", {"node_id": "new"}), ("delete_node", {"error": "boom"})]
    assert ran[0] == ("branch_node", {"node_id": NODE, "title": "T"}, PROJECT, USER.id, agent_router.DEFAULT_MODEL_ID)
    # the model sees the agent tools, the node outline and the selection, and gets each result back
    first = requests[0]
    assert {"branch_node", "write_node", "merge_nodes", "search_paper_evidence"} <= {t["function"]["name"] for t in first["tools"]}
    assert "write_node" in first["messages"][0]["content"]
    assert NODE in first["messages"][0]["content"] and f"selected: {NODE}" in first["messages"][0]["content"]
    assert requests[1]["messages"][-1] == {"role": "tool", "tool_call_id": "1", "content": '{"node_id": "new"}'}


def test_tool_rounds_are_bounded(agent):
    c, script, requests, ran = agent
    script += [[tool_call(str(i), "branch_node", {"node_id": NODE})] for i in range(agent_router.MAX_ROUNDS - 1)]
    script.append([{"text": "done"}])
    assert ask(c).json()["reply"] == "done"
    assert requests[-1]["tool_choice"] == "none" and requests[0]["tool_choice"] is None


def test_provider_error_and_unknown_model_are_reported(agent):
    c, script, *_ = agent
    script.append([{"error": "rate limited"}])
    assert ask(c).status_code == 502
    assert ask(c, model="no/such-model").status_code == 400


LONG = "word " * 200  # over LONG_REPLY


def test_long_chat_answer_is_sent_back_once_to_go_in_the_tree(agent):
    c, script, requests, ran = agent
    script += [[{"text": LONG}], [tool_call("1", "write_node", {"parent_id": NODE, "title": "T", "body": "B"})], [{"text": "Saved T."}]]
    assert ask(c, "What does the literature say about X?").json()["reply"] == "Saved T."
    assert requests[1]["messages"][-1] == {"role": "user", "content": agent_router.NUDGE}
    assert requests[1]["messages"][-2] == {"role": "assistant", "content": LONG.strip()}
    assert [r[0] for r in ran] == ["write_node"]


def test_nudge_is_once_and_only_for_long_answers_with_nothing_written(agent):
    c, script, requests, ran = agent
    script += [[{"text": LONG}], [{"text": LONG}]]  # the model insists: the second answer is returned as is
    assert ask(c).json()["reply"] == LONG.strip() and len(requests) == 2

    script += [[{"text": "short"}]]
    assert ask(c).json()["reply"] == "short" and len(requests) == 3

    script += [[tool_call("1", "write_node", {"parent_id": NODE, "title": "T", "body": "B"})], [{"text": LONG}]]
    assert ask(c).json()["reply"] == LONG.strip() and len(requests) == 5  # already wrote: no nudge


def test_model_that_ignores_tool_choice_none_on_the_last_round_still_gets_a_reply(agent):
    c, script, requests, ran = agent
    # every round, including the one that forbids tools, comes back as a tool call
    script += [[tool_call(str(i), "branch_node", {"node_id": NODE})] for i in range(agent_router.MAX_ROUNDS)]
    r = ask(c)
    assert r.status_code == 200
    body = r.json()
    assert body["reply"] == agent_router.NO_ANSWER
    assert len(body["tool_calls"]) == agent_router.MAX_ROUNDS - 1  # the call made while tools were forbidden is not run


def hurried(requests):
    return [r["messages"][-1] == {"role": "user", "content": agent_router.WRITE_NOW} for r in requests]


def test_research_without_a_node_by_round_three_gets_told_to_write_once(agent):
    c, script, requests, ran = agent
    script += [[tool_call(str(i), "search_papers", {"query": "q"})] for i in range(4)]
    script += [[tool_call("w", "write_node", {"parent_id": NODE, "title": "T", "body": "B"})], [{"text": "Saved T."}]]
    assert ask(c, "What does the literature say about X?").json()["reply"] == "Saved T."
    assert hurried(requests) == [False, False, True, False, False, False]  # once, before the 3rd model call


def test_no_write_now_when_a_node_is_written_or_nothing_was_researched(agent):
    c, script, requests, ran = agent
    script += [[tool_call("1", "write_node", {"parent_id": NODE, "title": "T", "body": "B"})]]
    script += [[tool_call(str(i), "search_papers", {"query": "q"})] for i in range(2)] + [[{"text": "done"}]]
    ask(c)
    assert not any(hurried(requests))

    requests.clear()
    script += [[tool_call(str(i), "branch_node", {"node_id": NODE})] for i in range(3)] + [[{"text": "done"}]]
    ask(c, "Add three branches")
    assert not any(hurried(requests))
