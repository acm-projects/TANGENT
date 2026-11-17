"""Compact, resolve and reopen a card.

Compact: the card's own model summarises its thread (everything that card's model sees: the root down to it, merged
sources included) into a new child card, node_type "compact", titled "Compacted". It is a fresh start: a card at or
below a compact card is sent the summary and the messages from the compact card down, nothing above it.
Resolve: a marker: the card is stamped with how its branch ended (`nodes.resolved = {by, at, kind}`, kind one of
ENDINGS; a stamp without one is "resolved"); nothing else changes.
Reopen: the stamp comes off. Any work on a resolved card or under it reopens it (reopen_for_work).
"""

from datetime import datetime, timezone
from typing import Mapping, Sequence
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.context.flatten import flatten, to_provider_messages
from app.context.plan import PlanItem, build_plan
from app.context.schemas import ENDINGS, PathNode
from app.core.openrouter import DEFAULT_MODEL_ID, get_model_or_400, stream_openrouter
from app.models import Node

TITLE = "Compacted"
COMPACT_PROMPT = (
    "Compact this conversation so a fresh model can continue it without the original. Write a dense summary: the "
    "question being researched and how it was framed, every finding with the sources it rests on (keep citations "
    "and evidence ids exactly as they appear), what was ruled out and why, and the open questions. No preamble; "
    "plain markdown, as short as the content allows."
)

_CHAIN_SQL = text("""
    WITH RECURSIVE up(id, depth) AS (
      SELECT CAST(:node_id AS uuid), 0
      UNION ALL
      SELECT n.parent_id, up.depth + 1 FROM nodes n JOIN up ON n.id = up.id WHERE n.parent_id IS NOT NULL
    )
    SELECT n.id, n.resolved FROM up JOIN nodes n USING (id) ORDER BY up.depth
""")


def cut_at_compact(plan: Sequence[PlanItem], nodes: Mapping[str, PathNode]) -> list[PlanItem]:
    """The thread from its last compact card on: the summary stands in for everything above it.
    shortcut: only a compact card on the main thread cuts; one inside a merged branch is read whole, fine while
    merges are rare and short."""
    starts = [i for i, item in enumerate(plan) if isinstance(item, str) and nodes[item].node_type == "compact"]
    return list(plan[starts[-1]:]) if starts else list(plan)


def thread_plan(path: Sequence[PathNode], tip: str) -> list[PlanItem]:
    """The reading plan for `tip`'s model: every ancestor once (merges included), cut at the last compact card."""
    nodes = {node.id: node for node in path}
    parents = {node.id: node.merge_source_ids or ([node.parent_id] if node.parent_id else []) for node in path}
    order = {node.id: (node.created_at, node.id) for node in path}
    return cut_at_compact(build_plan(tip, parents, order), nodes)


def _cards(plan: Sequence[PlanItem]) -> int:
    return sum(1 if isinstance(item, str) else sum(_cards(b["plan"]) for b in item["merge"]) for item in plan)


async def _summarise(db: AsyncSession, node: Node, model: str) -> tuple[str, int, int]:
    """(summary, cards summarised, tokens) of node's thread, written by `model`."""
    from app.routers.nodes_router import _GRAPH_SQL  # here: nodes_router imports this module

    rows = (await db.execute(_GRAPH_SQL, {"node_id": node.id})).all()
    path = [PathNode(id=r.id, parent_id=r.parent_id, title=r.title, chats=r.chats, model=r.model,
                     created_at=r.created_at, node_type=r.node_type,
                     merge_source_ids=[str(s) for s in r.merge_source_ids]) for r in rows]
    plan = thread_plan(path, str(node.id))
    segments = flatten(plan, {p.id: p for p in path})
    if not any(segment.messages for segment in segments):
        raise HTTPException(409, "There's nothing on this card's thread to compact yet")
    messages = [{"role": "system", "content": "You compact research conversations."},
                *to_provider_messages(segments, COMPACT_PROMPT)]
    out, tokens = [], 0
    # shortcut: the request's transaction stays open for the model call (seconds); fine at this scale, release the
    # connection first (as send_message does) if the pool runs short
    async for chunk in stream_openrouter(messages, model):
        if "error" in chunk:
            raise HTTPException(502, "The model couldn't compact this thread; try again")
        out.append(chunk.get("text", ""))
        tokens += int((chunk.get("usage") or {}).get("completion_tokens") or 0)
    summary = "".join(out).strip()
    if not summary:
        raise HTTPException(502, "The model returned an empty summary; try again")
    return summary, _cards(plan), tokens


async def compact(db: AsyncSession, node: Node, user_id: UUID, *, model: str | None = None) -> Node:
    """A new compact child of `node` holding the summary of node's thread (flushed, not committed)."""
    from app.routers.nodes_router import _create_child

    model = model or node.model or DEFAULT_MODEL_ID
    get_model_or_400(model)
    summary, cards, tokens = await _summarise(db, node, model)
    message = {"role": "assistant", "content": summary, "seq": 0,
               "created_at": datetime.now(timezone.utc).isoformat(), "compact": True, "compacted_from": cards}
    child = await _create_child(db, tree_id=node.tree_id, project_id=node.project_id, parent_id=node.id,
                                user_id=user_id, chats=[message])
    child.node_type, child.title, child.model, child.tokens = "compact", TITLE, model, tokens
    await db.flush()
    return child


async def resolve(db: AsyncSession, node: Node, user_id: UUID, by: str, kind: str = "resolved") -> Node:
    """Stamp how node's branch ended, `kind` (ENDINGS), by `by` ("user" | "gent"). Stamped already: returns it as is."""
    if kind not in ENDINGS:
        raise ValueError(f"unknown ending: {kind}")
    if not node.resolved:
        node.resolved = {"by": by, "at": datetime.now(timezone.utc).isoformat(), "kind": kind}
        await db.flush()
    return node


async def reopen(db: AsyncSession, node: Node, user_id: UUID) -> None:
    """Take a resolved card's stamp off."""
    if node.resolved:
        node.resolved = None
        await db.flush()


async def reopen_for_work(db: AsyncSession, node_id: UUID, user_id: UUID) -> list[UUID]:
    """Work is about to happen on `node_id`: reopen every resolved card at or above it. Returns their ids.
    shortcut: walks the main parent link only, so work under a merge of a resolved branch doesn't reopen it."""
    reopened = []
    for row in (await db.execute(_CHAIN_SQL, {"node_id": node_id})).all():
        if row.resolved:
            await reopen(db, await db.get(Node, row.id), user_id)
            reopened.append(row.id)
    return reopened


def conclusion(compact_node: Node, limit: int = 400) -> str:
    """A Compacted card's summary, trimmed (Gent's compact() result)."""
    chats = compact_node.chats or []
    body = (chats[0].get("content") or "").strip() if chats else ""
    return body if len(body) <= limit else body[:limit].rsplit(" ", 1)[0] + "…"
