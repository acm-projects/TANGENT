import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.agent import thread


@pytest.fixture
def stored(monkeypatch):
    rows = []

    async def fake_append(project_id, user_id, run_id, batch, notes):
        rows.extend(batch)

    monkeypatch.setattr(thread, "append", fake_append)
    return rows


def run():
    return SimpleNamespace(project_id=uuid4(), user_id=uuid4(), notes=[])


def test_joins_streamed_fragments_and_keeps_only_what_the_chat_needs(stored):
    async def scenario():
        rec = thread.Recorder(run())
        rec.emit("task", {"text": "go"})
        rec.emit("note", {"turn": 1, "text": "Look "})
        rec.emit("note", {"turn": 1, "text": "around."})
        rec.emit("node_token", {"id": "n", "text": "tok"})  # drives the board only
        rec.emit("tool", {"turn": 1, "id": "c1", "name": "ls", "args": {}})
        rec.emit("reasoning", {"turn": 2, "depth": "deep", "text": "hm"})
        rec.close()
        await rec.writer
        assert [r["type"] for r in stored] == ["task", "note", "tool", "reasoning"]
        assert stored[1] == {"type": "note", "turn": 1, "text": "Look around."}



    asyncio.run(scenario())


def test_a_listener_gets_everything_so_far_then_what_comes_next_but_never_the_users_own_words(stored):
    async def scenario():
        rec = thread.Recorder(run())
        rec.emit("task", {"text": "go"})
        rec.emit("note", {"turn": 1, "text": "Hi"})
        so_far, queue = rec.listen()
        assert [e["type"] for e in so_far] == ["task", "note"]
        rec.emit("said", {"text": "skip that"})
        rec.emit("reply", {"turn": 1, "text": "Done."})
        rec.close()
        frames = []
        while (frame := await queue.get()) is not None:
            frames.append(frame)
        assert len(frames) == 1 and frames[0].startswith("event: reply")
        await rec.writer
        assert [r["type"] for r in stored] == ["task", "note", "said", "reply"]



    asyncio.run(scenario())


def test_a_failing_write_does_not_stop_the_run(monkeypatch):
    async def scenario():
        async def broken(*args):
            raise RuntimeError("db down")

        monkeypatch.setattr(thread, "append", broken)
        rec = thread.Recorder(run())
        rec.emit("reply", {"turn": 1, "text": "x"})
        rec.close()
        await asyncio.wait_for(rec.writer, 1)

    asyncio.run(scenario())
