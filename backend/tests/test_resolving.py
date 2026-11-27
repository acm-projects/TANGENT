from datetime import datetime, timedelta, timezone

from app import resolving
from app.context.flatten import flatten, to_provider_messages
from app.context.schemas import PathNode

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def card(id, parent=None, n=0, node_type=None, chats=None):
    return PathNode(id=id, parent_id=parent, created_at=T0 + timedelta(minutes=n), node_type=node_type,
                    chats=chats if chats is not None else [
                        {"role": "user", "content": f"q {id}", "seq": 0, "created_at": T0},
                        {"role": "assistant", "content": f"a {id}", "seq": 1, "created_at": T0}])


def test_a_compact_card_on_the_thread_is_a_fresh_start():
    summary = [{"role": "assistant", "content": "the gist", "seq": 0, "created_at": T0, "compact": True,
                "compacted_from": 2}]
    path = [card("root"), card("a", "root", 1), card("c", "a", 2, "compact", summary), card("b", "c", 3)]
    plan = resolving.thread_plan(path, "b")
    assert plan == ["c", "b"]
    messages = to_provider_messages(flatten(plan, {p.id: p for p in path}), "next")
    assert messages[0]["role"] == "user" and "the gist" in messages[0]["content"]
    assert not any("q root" in m["content"] or "a a" in m["content"] for m in messages)


def test_without_a_compact_card_the_whole_thread_is_read():
    path = [card("root"), card("a", "root", 1)]
    assert resolving.thread_plan(path, "a") == ["root", "a"]
