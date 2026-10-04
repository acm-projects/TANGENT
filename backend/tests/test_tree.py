from datetime import datetime, timezone

import pytest

from app.context.flatten import flatten, to_provider_messages
from app.context.schemas import ChatMessage, PathNode
from app.context.tree import build_merge_chats, find_lca, next_fork_index, path_below

NOW = datetime(2026, 10, 4, tzinfo=timezone.utc)
OLD = datetime(2026, 1, 1, tzinfo=timezone.utc)

#   root
#   └─ lca
#      ├─ a1 ─ a2
#      └─ b1
PARENTS = {"root": None, "lca": "root", "a1": "lca", "a2": "a1", "b1": "lca"}


def msg(role, content, seq=0):
    return ChatMessage(role=role, content=content, seq=seq, created_at=OLD)


def test_next_fork_index():
    assert next_fork_index([]) == 0
    assert next_fork_index([0, 1, 4]) == 5


def test_find_lca_and_paths():
    assert find_lca(PARENTS, "a2", "b1") == "lca"
    assert path_below(PARENTS, "lca", "a2") == ["a1", "a2"]
    assert path_below(PARENTS, "lca", "b1") == ["b1"]


def test_find_lca_rejects_bad_pairs():
    with pytest.raises(ValueError):
        find_lca(PARENTS, "a2", "a2")
    with pytest.raises(ValueError):
        find_lca(PARENTS, "a2", "lca")  # ancestor, not a sibling branch
    with pytest.raises(ValueError):
        find_lca({"x": None, "y": None}, "x", "y")


def test_build_merge_chats_tags_and_renumbers():
    chats = {
        "a1": [msg("user", "a1q"), msg("assistant", "a1a")],
        "a2": [msg("user", "a2q"), msg("assistant", "a2a")],
        "b1": [msg("user", "bq"), msg("assistant", "ba")],
    }
    out = build_merge_chats(chats, ["a1", "a2"], ["b1"], NOW)
    assert [m.content for m in out] == ["a1q", "a1a", "a2q", "a2a", "bq", "ba"]
    assert [m.branch_source for m in out] == ["a"] * 4 + ["b"] * 2
    assert [m.seq for m in out] == list(range(6))
    assert all(m.created_at == NOW for m in out)
    assert chats["a1"][0].branch_source is None  # sources untouched


def test_merge_output_flattens_to_one_branch_block():
    merged = build_merge_chats(
        {"a1": [msg("user", "aq"), msg("assistant", "aa")], "b1": [msg("user", "bq"), msg("assistant", "ba")]},
        ["a1"], ["b1"], NOW,
    )
    path = [PathNode(id="lca", chats=[msg("user", "q"), msg("assistant", "a")]), PathNode(id="m", chats=merged)]
    out = to_provider_messages(flatten(path), "next")
    assert [m["role"] for m in out] == ["user", "assistant", "user"]
    assert "<branch_a>" in out[2]["content"] and "<branch_b>" in out[2]["content"]
    assert out[2]["content"].endswith("next")
