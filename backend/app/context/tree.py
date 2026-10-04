"""
Pure tree helpers for fork/merge. No DB: the endpoint loads a {node_id: parent_id}
map (root -> None) and per-node chats, then calls these.
"""

from datetime import datetime
from typing import Iterable, Mapping, Optional, Sequence

from app.context.schemas import ChatMessage

Parents = Mapping[str, Optional[str]]


def next_fork_index(sibling_indexes: Iterable[int]) -> int:
    # Racy by itself; the DB unique (parent_id, fork_index) is the real guard (retry on violation).
    return max(sibling_indexes, default=-1) + 1


def _ancestors(parents: Parents, node: str) -> list[str]:
    """node, parent, ..., root."""
    out: list[str] = []
    cur: Optional[str] = node
    while cur is not None:
        out.append(cur)
        cur = parents[cur]
    return out


def find_lca(parents: Parents, a: str, b: str) -> str:
    if a == b:
        raise ValueError("cannot merge a node with itself")
    a_anc = set(_ancestors(parents, a))
    for n in _ancestors(parents, b):
        if n in a_anc:
            if n in (a, b):
                raise ValueError("cannot merge a node with its own ancestor")
            return n
    raise ValueError("nodes share no common ancestor")


def path_below(parents: Parents, lca: str, leaf: str) -> list[str]:
    """Node ids strictly below lca down to leaf, top first."""
    up = _ancestors(parents, leaf)
    if lca not in up:
        raise ValueError("lca is not an ancestor of leaf")
    return up[: up.index(lca)][::-1]


def build_merge_chats(
    chats_by_node: Mapping[str, Sequence[ChatMessage]],
    path_a: Sequence[str],
    path_b: Sequence[str],
    now: datetime,
) -> list[ChatMessage]:
    """Snapshot both branches into one chats array, tagged a/b, seq renumbered."""
    out: list[ChatMessage] = []
    for tag, path in (("a", path_a), ("b", path_b)):
        for node_id in path:
            for m in chats_by_node[node_id]:
                out.append(m.model_copy(update={"branch_source": tag, "seq": len(out), "created_at": now}))
    return out
