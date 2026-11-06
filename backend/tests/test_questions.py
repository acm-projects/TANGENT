"""Question cards (app/questions.py) and Gent waiting for their answers: no database (the card rows are faked)."""
import asyncio
import os
import uuid

_dummies = {"DATABASE_URL": "postgresql://dummy@localhost/dummy", "JWT_SECRET_KEY": "test-secret"}
_added = [k for k in _dummies if k not in os.environ]
os.environ.update({k: _dummies[k] for k in _added})

import pytest
from fastapi import HTTPException

from app import questions
from app.agent import tools
from app.models import Node
from app.routers import nodes_router

for _k in _added:
    del os.environ[_k]


def q(prompt, *labels, **extra):
    return {"prompt": prompt, "options": [{"label": l} for l in labels], **extra}


class FakeDb:
    def __init__(self):
        self.rows = {}

    async def get(self, model, node_id):
        return self.rows.get(node_id)


@pytest.fixture
def db(monkeypatch):
    fake = FakeDb()

    async def create_child(db, *, tree_id, project_id, parent_id, user_id, chats=None):
        child = Node(id=uuid.uuid4(), tree_id=tree_id, project_id=project_id, parent_id=parent_id, node_type="standard")
        fake.rows[child.id] = child
        return child

    monkeypatch.setattr(nodes_router, "_create_child", create_child)
    return fake


def test_clean_checks_and_keeps_only_a_real_recommendation():
    out = questions.clean([q("Which era?", "1970s", "Today", recommended="Today", about="angle"),
                           q("Scope?", "US", "World", recommended="Mars")])
    assert out[0]["recommended"] == "Today" and out[0]["about"] == "angle" and out[0]["type"] == "single"
    assert out[1]["recommended"] is None and out[1]["about"] == "intent"
    with pytest.raises(HTTPException):
        questions.clean([q("Only one?", "A")])
    with pytest.raises(HTTPException):
        questions.clean([q(f"Q{i}", "A", "B") for i in range(5)])


def test_a_chain_asks_one_question_per_card_and_every_answer_is_a_branch(db):
    async def scenario():
        root = Node(id=uuid.uuid4(), tree_id=uuid.uuid4(), project_id=uuid.uuid4())
        asked = questions.clean([q("Which era?", "1970s", "Today"), q("Which sources?", "Papers", "News", type="multi")])
        first = await questions.ask(db, root, uuid.uuid4(), asked, {"by": "node", "model": "m", "origin": str(root.id)})
        assert first.node_type == "question" and first.question["prompt"] == "Which era?"

        a = await questions.answer(db, first, uuid.uuid4(), "Today")
        second = a["node"]
        assert not a["final"] and second.node_type == "question" and second.question["prompt"] == "Which sources?"
        assert second.question["chain"] == str(first.id)

        # the same answer again leads back to its branch; a different one opens a sibling
        assert (await questions.answer(db, first, uuid.uuid4(), "Today"))["node"] is second
        other = await questions.answer(db, first, uuid.uuid4(), "1970s")
        assert other["node"] is not second and not other["existing"]
        assert [x["answer"] for x in first.question["answers"]] == ["Today", "1970s"]

        last = await questions.answer(db, second, uuid.uuid4(), ["News", "Papers", "my blog"])
        assert last["final"] and last["node"].node_type == "standard" and last["node"].model == "m"
        assert last["node"].title == "Papers, News, my blog"  # named for the answer, not the message that starts it
        assert last["trail"] == [{"prompt": "Which era?", "answer": "Today"},
                                 {"prompt": "Which sources?", "answer": ["Papers", "News", "my blog"]}]
        assert "A: Papers, News, my blog" in questions.trail_text(last["trail"])

    asyncio.run(scenario())


def test_remap_points_a_copied_card_at_the_copy():
    a, b = uuid.uuid4(), uuid.uuid4()
    card = {"prompt": "x", "chain": str(a), "answers": [{"answer": "y", "node_id": str(a), "by": "user"}],
            "asker": {"by": "node", "origin": str(a)}}
    out = questions.remap(card, {a: b})
    assert out["chain"] == str(b) and out["answers"][0]["node_id"] == str(b) and out["asker"]["origin"] == str(b)


def gent_run():
    return tools.Run(project_id=uuid.uuid4(), user_id=uuid.uuid4(), model="m", cwd=uuid.uuid4(), owner=True)


def test_an_answer_wakes_gents_wait_for_a_question(monkeypatch):
    async def no_names(run, updates):
        pass

    monkeypatch.setattr(tools, "_name_cards", no_names)

    async def scenario():
        run = gent_run()
        waiting = asyncio.create_task(tools.wait(run, **{"for": "question"}))
        await asyncio.sleep(0)
        run.post({"kind": "answer", "address": "1.2", "id": "x"})  # not what he waits for
        await asyncio.sleep(0)
        assert not waiting.done()
        run.post({"kind": "question", "id": "c", "chain": "c", "answer": "Today", "branch": "b", "final": True})
        got = await asyncio.wait_for(waiting, 1)
        assert [u["kind"] for u in got["updates"]] == ["question"]
        assert [u["kind"] for u in run.updates] == ["answer"]  # left for the next wait

    asyncio.run(scenario())


def test_waiting_for_a_question_has_no_timeout():
    async def scenario():
        run = gent_run()
        waiting = asyncio.create_task(tools.wait(run, timeout=1, **{"for": "question"}))
        await asyncio.sleep(1.3)  # past the timeout he asked for
        assert not waiting.done()
        waiting.cancel()  # Stop still ends it

    asyncio.run(scenario())


def test_tell_gent_posts_the_update_and_logs_it(monkeypatch):
    from app.agent import router

    run = gent_run()
    events = []
    run.emit = lambda e, d: events.append(e)
    monkeypatch.setitem(router._runs, (run.user_id, run.project_id), run)
    nodes_router.tell_gent(run.user_id, run.project_id, {"kind": "question", "id": "c", "final": False})
    assert run.updates == [{"kind": "question", "id": "c", "final": False}] and run.arrived.is_set()
    assert events == ["question_answered", "tree"]
