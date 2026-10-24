"""Debate context = exactly what a normal chat message would send: the parent chain, root to leaf.

This mirrors app/context/flatten.py (`_serialize_node`): messages tagged with `branch_source` (a merge node's
two snapshots) collapse into ONE user turn at the position of the first tagged message. Merge sources are NOT
walked separately, because a merge node already carries both branches inside its own chats.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional, Protocol


@dataclass
class NodeRow:
    id: str
    chats: list[dict[str, Any]] = field(default_factory=list)


class NodeStore(Protocol):
    async def path(self, node_id: str) -> list[NodeRow]:
        """Root -> leaf, the node itself last. Empty when the node is missing or not visible."""
        ...


@dataclass
class LineageContext:
    text: str
    node_ids: list[str]
    summarized: bool = False
    dropped_node_ids: list[str] = field(default_factory=list)


def default_count_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _role(raw: Any) -> str:
    return "assistant" if raw in ("assistant", "llm") else str(raw or "user")


def _render_branches(branches: dict[str, list[dict[str, Any]]]) -> str:
    """branches is keyed by branch_source (the source leaf node id that nodes_router.merge_nodes writes; older data may
    use "a"/"b"), in order of first appearance, and labelled a, b in that order. Mirrors app/context/flatten.py."""
    parts = ["The user merged two conversation branches into this one. Both transcripts follow."]
    for label, msgs in zip("abcdefgh", branches.values()):
        if not msgs:
            continue
        body = "\n\n".join(f"{_role(m.get('role')).capitalize()}: {m.get('content', '')}" for m in msgs)
        parts.append(f"<branch_{label}>\n{body}\n</branch_{label}>")
    return "\n\n".join(parts)


def serialize_node(chats: list[dict[str, Any]]) -> list[tuple[str, str]]:
    branches: dict[str, list[dict[str, Any]]] = {}
    for m in chats:
        if m.get("branch_source"):
            branches.setdefault(str(m["branch_source"]), []).append(m)
    out: list[tuple[str, str]] = []
    emitted = False
    for m in chats:  # array order is the order
        src = m.get("branch_source")
        if not src:
            out.append((_role(m.get("role")), str(m.get("content", ""))))
        elif not emitted:
            out.append(("user", _render_branches(branches)))
            emitted = True
    return out


def render_node(row: NodeRow) -> str:
    return "\n".join(f"{role}: {content}" for role, content in serialize_node(row.chats))


async def collect_lineage(store: NodeStore, node_id: str) -> list[NodeRow]:
    return [r for r in await store.path(node_id) if r.chats]


async def build_lineage_context(
    store: NodeStore,
    node_id: str,
    *,
    token_budget: int,
    count_tokens: Callable[[str], int] = default_count_tokens,
    summarize: Optional[Callable[[list[str]], Awaitable[str]]] = None,
    summary_reserve: int = 400,
) -> LineageContext:
    rows = await collect_lineage(store, node_id)
    blocks = [(row, f"--- node {row.id} ---\n{render_node(row)}") for row in rows]
    total = sum(count_tokens(b) for _, b in blocks)
    if total <= token_budget:
        return LineageContext(text="\n\n".join(b for _, b in blocks), node_ids=[r.id for r, _ in blocks])
    if not blocks:
        return LineageContext(text="", node_ids=[])

    limit = max(1, token_budget - summary_reserve)
    kept: list[tuple[NodeRow, str]] = []
    used = 0
    for row, text in reversed(blocks):
        cost = count_tokens(text)
        if kept and used + cost > limit:
            break
        kept.append((row, text))
        used += cost
    kept.reverse()

    newest_row, newest_text = kept[-1]
    while count_tokens(newest_text) > limit and len(newest_text) > 40:
        newest_text = newest_text[max(1, len(newest_text) // 10):]
    kept[-1] = (newest_row, newest_text)

    kept_ids = {r.id for r, _ in kept}
    dropped = [(r, t) for r, t in blocks if r.id not in kept_ids]
    if summarize and dropped:
        summary = await summarize([t for _, t in dropped])
    else:
        summary = f"(earlier conversation omitted: {len(dropped)} nodes)"
    parts = [f"[earlier conversation, summarized]\n{summary}"] if dropped else []
    parts += [t for _, t in kept]
    return LineageContext(
        text="\n\n".join(parts),
        node_ids=[r.id for r, _ in kept],
        summarized=bool(dropped),
        dropped_node_ids=[r.id for r, _ in dropped],
    )