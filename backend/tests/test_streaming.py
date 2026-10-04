import asyncio

import pytest

from app.core.leaf import NotLeafError, assert_promptable, is_leaf
from app.core.streaming import sse, stream_events

PARENTS = {"root": None, "mid": "root", "leaf": "mid"}


def test_leaf_checks():
    assert is_leaf("leaf", PARENTS) and not is_leaf("mid", PARENTS)
    assert_promptable("leaf", PARENTS)
    with pytest.raises(NotLeafError):
        assert_promptable("root", PARENTS)
    with pytest.raises(KeyError):
        assert_promptable("ghost", PARENTS)


def test_sse_framing():
    assert sse("token", {"text": "hi"}) == 'event: token\ndata: {"text": "hi"}\n\n'


def collect(chunks, on_done):
    async def run():
        return [f async for f in stream_events(chunks, on_done)]
    return asyncio.run(run())


def test_tokens_then_done_and_persists_full_reply():
    saved = []

    async def chunks():
        yield "he"
        yield "llo"

    async def on_done(text):
        saved.append(text)

    frames = collect(chunks(), on_done)
    assert frames == [sse("token", {"text": "he"}), sse("token", {"text": "llo"}), sse("done", {})]
    assert saved == ["hello"]


def test_upstream_failure_emits_error_and_no_done_and_no_persist():
    saved = []

    async def chunks():
        yield "he"
        raise RuntimeError("boom")

    async def on_done(text):
        saved.append(text)

    frames = collect(chunks(), on_done)
    assert frames[-1] == sse("error", {"message": "boom"})
    assert not any(f.startswith("event: done") for f in frames)
    assert saved == []
