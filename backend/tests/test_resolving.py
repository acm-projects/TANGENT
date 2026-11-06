import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

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


class FakeDB:
    """Just enough of an AsyncSession for reopen / reopen_for_work."""

    def __init__(self, nodes, used=False, chain=()):
        self.nodes, self.used, self.chain, self.deleted = nodes, used, list(chain), []

    async def get(self, _model, id):
        return self.nodes.get(id)

    async def execute(self, statement, params):
        if "WITH RECURSIVE up" in str(statement):
            return SimpleNamespace(all=lambda: self.chain)
        return SimpleNamespace(scalar_one=lambda: self.used)

    async def delete(self, obj):
        self.deleted.append(obj.id)

    async def flush(self):
        pass


def node(id, resolved=None, chats=None):
    return SimpleNamespace(id=id, resolved=resolved, chats=chats or [{"role": "assistant", "content": "s"}])


def test_resolve_stamps_and_reopen_unstamps():
    a = uuid.uuid4()
    nodes = {a: node(a)}
    db = FakeDB(nodes)
    assert asyncio.run(resolving.resolve(db, nodes[a], uuid.uuid4(), "gent")) is nodes[a]
    assert nodes[a].resolved["by"] == "gent" and db.deleted == []
    asyncio.run(resolving.reopen(db, nodes[a], uuid.uuid4()))
    assert nodes[a].resolved is None


def test_any_work_on_or_under_a_resolved_card_reopens_it():
    root, a, kid = (uuid.uuid4() for _ in range(3))
    stamp = {"by": "user", "at": "t"}
    row = lambda id, resolved=None: SimpleNamespace(id=id, resolved=resolved)  # noqa: E731
    under_nodes = {a: node(a, dict(stamp))}
    under = FakeDB(under_nodes, chain=[row(kid), row(a, stamp), row(root)])
    assert asyncio.run(resolving.reopen_for_work(under, kid, uuid.uuid4())) == [a]
    assert under_nodes[a].resolved is None
    clear = FakeDB({}, chain=[row(kid), row(root)])
    assert asyncio.run(resolving.reopen_for_work(clear, kid, uuid.uuid4())) == []
