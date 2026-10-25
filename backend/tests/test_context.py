from debate.context import NodeRow, build_lineage_context, serialize_node
from helpers import run


class MemStore:
    """Path store like PgNodeStore: root -> leaf for the requested node."""

    def __init__(self, rows, parents):
        self.rows, self.parents = {r.id: r for r in rows}, parents

    async def path(self, node_id):
        out, cur = [], node_id
        while cur in self.rows:
            out.append(self.rows[cur])
            cur = self.parents.get(cur)
        return list(reversed(out))


def row(i, text=None, chats=None):
    return NodeRow(
        id=i,
        chats=chats or [{"role": "user", "content": text or f"question {i}"}, {"role": "assistant", "content": f"answer {i}"}],
    )


def chain(n, text=None):
    rows = [row(f"n{i}", text=text) for i in range(n)]
    return MemStore(rows, {f"n{i}": f"n{i-1}" for i in range(1, n)})


def test_lineage_runs_root_to_leaf_and_skips_siblings():
    rows = [row("n1"), row("n2"), row("n3"), row("n2b")]
    store = MemStore(rows, {"n2": "n1", "n3": "n2", "n2b": "n1"})
    ctx = run(build_lineage_context(store, "n3", token_budget=10_000))
    assert ctx.node_ids == ["n1", "n2", "n3"]
    assert ctx.text.index("question n1") < ctx.text.index("question n2") < ctx.text.index("question n3")
    assert "n2b" not in ctx.text and not ctx.summarized


def test_over_budget_summarizes_oldest_and_keeps_newest():
    store = chain(10, text="x" * 400)
    calls = {}

    async def summarize(parts):
        calls["parts"] = parts
        return "SUMMARY"

    ctx = run(build_lineage_context(store, "n9", token_budget=550, summarize=summarize, summary_reserve=100))
    assert ctx.summarized and ctx.node_ids[-1] == "n9"
    assert ctx.text.startswith("[earlier conversation, summarized]\nSUMMARY")
    assert len(calls["parts"]) == len(ctx.dropped_node_ids) > 0
    assert set(ctx.node_ids).isdisjoint(ctx.dropped_node_ids)


def test_single_huge_node_is_trimmed_from_the_front():
    store = MemStore([row("n1", text="a" * 20_000 + "TAIL")], {})
    ctx = run(build_lineage_context(store, "n1", token_budget=500, summary_reserve=100))
    assert ctx.text.endswith("answer n1") and len(ctx.text) < 2_500


def test_missing_or_invisible_node_gives_empty_context():
    ctx = run(build_lineage_context(MemStore([], {}), "nope", token_budget=100))
    assert ctx.text == "" and ctx.node_ids == []


def test_empty_nodes_are_skipped():
    store = MemStore([row("a"), NodeRow(id="b", chats=[]), row("c")], {"b": "a", "c": "b"})
    ctx = run(build_lineage_context(store, "c", token_budget=10_000))
    assert ctx.node_ids == ["a", "c"]


def test_merge_node_snapshots_collapse_into_one_user_turn_like_the_chat_endpoint():
    chats = [
        {"role": "user", "content": "A1", "branch_source": "a"},
        {"role": "assistant", "content": "A2", "branch_source": "a"},
        {"role": "user", "content": "B1", "branch_source": "b"},
        {"role": "user", "content": "first prompt on the merge node", "branch_source": None},
    ]
    out = serialize_node(chats)
    assert [r for r, _ in out] == ["user", "user"]
    assert "<branch_a>" in out[0][1] and "A2" in out[0][1] and "<branch_b>" in out[0][1] and "B1" in out[0][1]
    assert out[1][1] == "first prompt on the merge node"


def test_stored_assistant_and_legacy_llm_roles_both_read_as_assistant():
    for role in ("assistant", "llm"):
        r = NodeRow(id="n", chats=[{"role": "user", "content": "hi"}, {"role": role, "content": "hello"}])
        ctx = run(build_lineage_context(MemStore([r], {}), "n", token_budget=1000))
        assert "assistant: hello" in ctx.text and "llm:" not in ctx.text


def test_merge_messages_tagged_with_source_leaf_ids_are_collapsed_like_flatten():
    from debate.context import serialize_node

    A, B = "5e4f9e0f-43d3-447f-886e-8e8ccc4639ab", "0b1c2d3e-0000-4000-8000-000000000001"
    out = serialize_node([
        {"role": "user", "content": "A1", "branch_source": A},
        {"role": "assistant", "content": "A2", "branch_source": A},
        {"role": "user", "content": "B1", "branch_source": B},
        {"role": "assistant", "content": "B2", "branch_source": B},
        {"role": "user", "content": "after merge", "branch_source": None},
    ])
    assert [r for r, _ in out] == ["user", "user"]
    assert "<branch_a>\nUser: A1\n\nAssistant: A2\n</branch_a>" in out[0][1]
    assert "<branch_b>\nUser: B1\n\nAssistant: B2\n</branch_b>" in out[0][1]
    assert out[1] == ("user", "after merge")
