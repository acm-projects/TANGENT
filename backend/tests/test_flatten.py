from datetime import datetime, timezone

from app.context.flatten import flatten, to_provider_messages
from app.context.schemas import ChatMessage, PathNode

NOW = datetime(2026, 9, 29, tzinfo=timezone.utc)


def msg(role, content, seq, branch=None):
    return ChatMessage(role=role, content=content, seq=seq, branch_source=branch, created_at=NOW)


def test_linear_path_preserves_order_and_node_boundaries():
    path = [
        PathNode(id="root", chats=[msg("user", "q1", 0), msg("assistant", "a1", 1)]),
        PathNode(id="leaf", chats=[msg("user", "q2", 0), msg("assistant", "a2", 1)]),
    ]
    segs = flatten(path)
    assert [s.node_id for s in segs] == ["root", "leaf"]
    out = to_provider_messages(segs, "q3")
    assert [m["content"] for m in out] == ["q1", "a1", "q2", "a2", "q3"]
    assert [m["role"] for m in out] == ["user", "assistant"] * 2 + ["user"]


def test_empty_nodes_are_skipped():
    path = [PathNode(id="root", chats=[]), PathNode(id="leaf", chats=[msg("user", "q", 0), msg("assistant", "a", 1)])]
    assert [s.node_id for s in flatten(path)] == ["leaf"]


def test_merge_node_collapses_branches_into_one_user_turn():
    merge_chats = [
        msg("user", "a-q", 0, "a"),
        msg("assistant", "a-a", 1, "a"),
        msg("user", "b-q", 2, "b"),
        msg("assistant", "b-a", 3, "b"),
        msg("user", "post-merge q", 4),
        msg("assistant", "post-merge a", 5),
    ]
    path = [
        PathNode(id="lca", chats=[msg("user", "shared q", 0), msg("assistant", "shared a", 1)]),
        PathNode(id="merge", chats=merge_chats),
    ]
    out = to_provider_messages(flatten(path), "next")
    roles = [m["role"] for m in out]
    assert roles == ["user", "assistant", "user", "assistant", "user"]  # strictly alternating
    block = out[2]["content"]
    assert "<branch_a>" in block and "<branch_b>" in block
    assert block.index("a-q") < block.index("b-q")
    assert "post-merge q" in block  # coalesced into the same user turn
    assert out[3]["content"] == "post-merge a"
    assert out[4]["content"] == "next"


def test_merge_with_only_one_branch_populated():
    path = [PathNode(id="m", chats=[msg("user", "a-q", 0, "a"), msg("assistant", "a-a", 1, "a")])]
    block = flatten(path)[0].messages[0].content
    assert "<branch_a>" in block and "<branch_b>" not in block


def test_does_not_mutate_input_and_is_deterministic():
    path = [PathNode(id="n", chats=[msg("user", "q", 0), msg("assistant", "a", 1)])]
    assert to_provider_messages(flatten(path), "x") == to_provider_messages(flatten(path), "x")
    assert path[0].chats[0].content == "q"
