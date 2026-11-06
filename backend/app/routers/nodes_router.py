import asyncio
import contextlib
import json
import logging
import re
from datetime import datetime, timezone
from typing import Literal, Optional, Union
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app import questions, resolving
from app.auth import get_current_user
from app.branch_scope import require_visible
from app.context.flatten import flatten, to_provider_messages
from app.context.schemas import NodeMeta, NodeOut, PathNode
from app.core.openrouter import DEFAULT_MODEL_ID, get_model_or_400, stream_openrouter
from app.database import AsyncSessionLocal, get_db_session
from app.models import Node, NodeMergeSource, Project, User
from app.papers import service as paper_service
from app.project_forking import (
    ForkInfo,
    build_fork_info,
    copy_exists_error,
    get_user_copy,
    get_write_target,
)

log = logging.getLogger(__name__)
router = APIRouter(prefix="/nodes", tags=["Nodes"])

# All ancestors through both parent links, under the caller's RLS identity.
_GRAPH_SQL = text("""
    WITH RECURSIVE anc(id) AS (
      SELECT CAST(:node_id AS uuid)
      UNION
      SELECT e.parent FROM anc
      JOIN (
        SELECT id AS child, parent_id AS parent FROM nodes WHERE parent_id IS NOT NULL
        UNION ALL
        SELECT node_id, source_leaf_id FROM node_merge_sources
      ) e ON e.child = anc.id
    )
    SELECT n.id::text AS id, n.parent_id::text AS parent_id, n.title, n.chats, n.model, n.created_at,
           n.node_type::text AS node_type,
           ARRAY(
             SELECT ms.source_leaf_id
             FROM node_merge_sources ms
             WHERE ms.node_id = n.id
             ORDER BY CASE WHEN ms.source_leaf_id = n.parent_id THEN 0 ELSE 1 END, ms.source_leaf_id
           ) AS merge_source_ids
    FROM nodes n JOIN anc USING (id)
""")


class MessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=20_000)
    model: str = DEFAULT_MODEL_ID
    # Regenerate the node's last reply: its last question is asked again and the new exchange replaces the old one.
    retry: bool = False


class MergeRequest(BaseModel):
    source_leaf_ids: list[UUID] = Field(min_length=2, max_length=8)  # 8 = labels flatten() renders (a-h)


class ForkNodeOut(NodeMeta):
    fork: Optional[ForkInfo] = None


class SplitRequest(BaseModel):
    # seq of the reply the node is cut after; it stays, everything after it moves down
    after_seq: int = Field(ge=0)
    # also start an empty tangent off the cut, beside the moved-down rest
    tangent: bool = False


class SplitOut(BaseModel):
    head: NodeMeta  # the node itself, now ending at the cut
    tail: NodeMeta  # its new only child: the rest of its messages, and every branch it had
    tangent: Optional[NodeMeta] = None
    fork: Optional[ForkInfo] = None


class NodeModelConflict(Exception):
    """Raised when a concurrent write tries to change a node's already-selected model."""


# Replies a user can stop, by (user id, prompted node id). Set by POST .../messages/stop, watched by send_message.
# shortcut: in-process only, so a stop must reach the worker that runs the stream; move to Redis pub/sub when scaling out.
_stops: dict[tuple[UUID, UUID], asyncio.Event] = {}

MAX_TOOL_ROUNDS = 4  # model turns that may call research tools; the next one must answer
ANSWER_NOW = ("Write your answer now, in plain text, from what you have found so far (say what you couldn't find). "
              "Keep it short and cited. Don't call any more tools.")
NOT_AN_ANSWER = ("That isn't an answer: it only names the question as open. Research it with your tools, then answer "
                 "it; the Open: line goes after an answer, never instead of one.")
# the date stamp context messages carry (context/flatten.py), when a model copies it onto its own reply
_DATE_STAMP = re.compile(r"^\s*\[\d{4}-\d{2}-\d{2}\]\s*")
_LEADING_TAGS = re.compile(r"^\s*(\[[^\]\n]{1,24}\]\s*)+")  # "[2026-11-05]", "[78:c2]": stamps or stray citations


def _non_answer(text: str) -> bool:
    """A reply that is only an "Open:" line (seen from the nemotron models): it names the question, answers nothing."""
    return _LEADING_TAGS.sub("", text).lower().startswith("open:")


MAX_CALLS_PER_ROUND = 5
TOOL_TIMEOUT = 75  # seconds per tool call; search_paper_evidence waits up to 60 for a PDF


# Quick thinking: the card's model may call think() to reason (low effort, natively) before its next reply.
THINK_TOOL = {"type": "function", "function": {
    "name": "think",
    "description": "Think before you answer: turns on quick reasoning for your next reply. Use it when the question "
                   "needs weighing (conflicting sources, several steps); skip it for simple ones.",
    "parameters": {"type": "object", "properties": {}, "required": []},
}}
# When the user's ask is ambiguous, the card's model asks instead of guessing: multiple-choice question cards under
# this card (app/questions.py), and its reply ends there; the research continues in the branch their answer opens.
ASK_USER_TOOL = {"type": "function", "function": {
    "name": "ask_user",
    "description": "Ask the user multiple-choice questions when you are unsure what they want (which reading of the "
                   "question, which scope, which option to pursue). Mark the option you'd pick as recommended. "
                   "Your reply ends after asking; the research continues in the branch their answer opens. Don't "
                   "ask what you can find out yourself.",
    "parameters": {"type": "object", "properties": {"questions": questions.QUESTIONS_PARAM}, "required": ["questions"]},
}}
NODE_TOOLS = [*paper_service.TOOLS, THINK_TOOL, ASK_USER_TOOL]


def _tool_row(name: str, args: dict, result: dict) -> dict:
    """What a tool call did, as one line for the chat ("searched papers for 'x'"); saved with the reply."""
    q = str(args.get("query") or "").strip()
    quoted = f" for “{q[:80]}”" if q else ""
    briefs = {
        "search_papers": f"Searched papers{quoted}",
        "get_paper": f"Read “{str(result.get('title') or args.get('paper_id') or 'a paper')[:80]}”",
        "search_paper_evidence": f"Searched {str(result.get('title') or 'a paper')[:60]}{quoted}",
        "search_sources": f"Searched your sources{quoted}",
        "add_source": f"Kept “{str(result.get('title') or args.get('paper') or 'a paper')[:70]}” in your sources",
        "web_search": f"Searched the web{quoted}",
        "think": "Quickly thought",
        "ask_user": "Asked you " + ("a question" if len(args.get("questions") or []) <= 1 else
                                    f"{len(args.get('questions') or [])} questions"),
    }
    return {"name": name, "brief": briefs.get(name, name), "ok": "error" not in result}


async def _ask_user(user_id: UUID, node_id: UUID, call: dict, model: str) -> dict:
    """The card's model asks the user: the first question card of the chain, under this card."""
    try:
        args = json.loads(call["function"]["arguments"] or "{}")
        asked = questions.clean(args.get("questions") if isinstance(args, dict) else None)
    except ValueError:
        return {"error": "The tool arguments were not valid JSON."}
    except HTTPException as exc:
        return {"error": exc.detail}
    async with AsyncSessionLocal() as db:
        await db.execute(text("SELECT set_config('app.current_user_id', :uid, true)"), {"uid": str(user_id)})
        parent = await db.get(Node, node_id)
        card = await questions.ask(db, parent, user_id, asked, {"by": "node", "model": model, "origin": str(node_id)})
        await db.commit()
        return {"ok": "Asked. The user answers on the question card under this one, and the research continues in "
                      "the branch their answer opens. Now end your reply in one short sentence saying what you asked "
                      "and why.", "card": str(card.id)}


async def _run_tool(call: dict, project_id: UUID, node_id: UUID) -> dict:
    """One tool call from the model -> its result. Failures become results the model can read, not errors."""
    name = call["function"]["name"]
    try:
        args = json.loads(call["function"]["arguments"] or "{}")
    except ValueError:
        return {"error": "The tool arguments were not valid JSON."}
    try:
        if node_id is None:
            return await asyncio.wait_for(paper_service.call_tool(name, args, project_id), TOOL_TIMEOUT)
        try:
            return await asyncio.wait_for(paper_service.call_tool(name, args, project_id, node_id), TOOL_TIMEOUT)
        except TypeError as exc:
            if "positional argument" not in str(exc):
                raise
            return await asyncio.wait_for(paper_service.call_tool(name, args, project_id), TOOL_TIMEOUT)
    except asyncio.TimeoutError:
        log.warning("tool %s timed out", name)
        return {"error": "The tool timed out; continue without it and say so."}


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _as_list(chats) -> list[dict]:
    return json.loads(chats) if isinstance(chats, str) else list(chats or [])


async def _sources_note(project_id: UUID, node_id: UUID) -> str:
    """Keep integrations that provide the legacy one-argument note hook working."""
    try:
        return await paper_service.project_sources_note(project_id, node_id)
    except TypeError as exc:
        if "positional argument" not in str(exc):
            raise
        return await paper_service.project_sources_note(project_id)


async def _load_path(
    db: AsyncSession, node_id: UUID, user_id: UUID
) -> tuple[list[PathNode], UUID]:
    rows = (await db.execute(_GRAPH_SQL, {"node_id": node_id})).all()
    if not rows:
        raise HTTPException(404, "Node not found")
    flags = (
        await db.execute(
            text("""
                SELECT n.project_id AS project_id,
                       p.created_by_id AS owner_id,
                       (
                         EXISTS (SELECT 1 FROM nodes c WHERE c.parent_id = n.id)
                         OR EXISTS (SELECT 1 FROM node_merge_sources ms WHERE ms.source_leaf_id = n.id)
                       ) AS has_child
                FROM nodes n JOIN projects p ON p.id = n.project_id
                WHERE n.id = :id
            """),
            {"id": node_id},
        )
    ).one()
    if flags.owner_id != user_id:
        # A sharee prompting the original is fine: the first write forks the project (see _prepare_write).
        # If they already forked, the original's node ids mean nothing in their copy, so redirect before spending tokens.
        user_copy = await get_user_copy(db, flags.project_id, user_id)
        if user_copy is not None:
            raise copy_exists_error(user_copy.id)
    if flags.has_child:
        # ARCHITECTURE.md §8: only leaves take prompts. The UI hint is not enforcement; this is.
        raise HTTPException(409, "Only a leaf node can be prompted; fork it instead")
    path = [
        PathNode(
            id=r.id,
            parent_id=r.parent_id,
            title=r.title,
            chats=r.chats,
            model=r.model,
            created_at=r.created_at,
            node_type=r.node_type,
            merge_source_ids=[str(source_id) for source_id in r.merge_source_ids],
        )
        for r in rows
    ]
    path.sort(key=lambda node: node.id == str(node_id))
    return path, flags.project_id


_background_tasks: set = set()


async def _reopen_for_work(user_id: UUID, node_id: UUID) -> list[str]:
    """Work is about to happen on node_id: reopen the resolved cards it falls under (app/resolving.py), in a session
    of its own and committed. Returns their ids."""
    async with AsyncSessionLocal() as session, session.begin():
        await session.execute(text("SELECT set_config('app.current_user_id', :uid, true)"), {"uid": str(user_id)})
        return [str(i) for i in await resolving.reopen_for_work(session, node_id, user_id)]


async def _prepare_write(user_id: UUID, project_id: UUID, node_id: UUID) -> tuple[UUID, Optional[dict]]:
    """Resolve where this write goes. Owner: the node itself. Sharee: fork the project first (own session,
    committed on its own so the copy exists whatever happens to the model call) and map the node into the copy.
    Returns (node id to write to, fork payload for the client or None)."""
    async with AsyncSessionLocal() as session, session.begin():
        await session.execute(
            text("SELECT set_config('app.current_user_id', :uid, true)"), {"uid": str(user_id)}
        )
        # Before anything is copied or sent to the model: a branch sharee may only prompt inside their branch.
        await require_visible(session, project_id, user_id, node_id)
        _, fork = await get_write_target(session, project_id, user_id)
        if fork is None:
            return node_id, None
        info = await build_fork_info(session, fork)
        write_node_id = fork.node_map[node_id]
        return write_node_id, {**info.model_dump(mode="json"), "node_id": str(write_node_id)}


async def _persist(
    user_id: UUID,
    write_node_id: UUID,
    user_text: str,
    assistant_text: str,
    model_id: str,
    response_tokens: Optional[int],
    citations: Optional[list[dict]] = None,
    replace_last: bool = False,
    author: str = "user",
    extras: Optional[dict] = None,
) -> None:
    """Append the exchange to nodes.chats of the node already resolved by _prepare_write. Own session: the
    request's may already be closed once the stream ends. `||` appends atomically (no read-modify-write);
    seq is the new array index. The node's model is set once; only provider-reported usage is added.
    `author` is who asked: "user", or "gent" for a question Gent asked. `extras` go on the reply: the tool rows it
    ran ({name, brief, ok}), its reasoning and thought_seconds."""
    base = "((chats - -1) - -1)" if replace_last else "chats"
    # a retry must still find the reply it replaces; if it's gone, the save fails rather than eat a question
    guard = "AND jsonb_array_length(chats) >= 2 AND chats->-1->>'role' = 'assistant'" if replace_last else ""
    now = datetime.now(timezone.utc).isoformat()
    async with AsyncSessionLocal() as session, session.begin():
        await session.execute(
            text("SELECT set_config('app.current_user_id', :uid, true)"), {"uid": str(user_id)}
        )
        result = await session.execute(
            text(f"""
                UPDATE nodes SET
                  title = COALESCE(title, left(CAST(:user_text AS text), 40)),
                  model = COALESCE(model, :model_id),
                  tokens = tokens + CAST(COALESCE(:response_tokens, 0) AS integer),
                  chats = {base}
                    || jsonb_build_array(jsonb_build_object(
                         'role', 'user', 'content', CAST(:user_text AS text), 'author', CAST(:author AS text),
                         'seq', jsonb_array_length({base}), 'created_at', CAST(:now AS text)))
                    || jsonb_build_array(jsonb_build_object(
                         'role', 'assistant', 'content', CAST(:assistant_text AS text),
                         'seq', jsonb_array_length({base}) + 1, 'created_at', CAST(:now AS text),
                         'citations', CAST(:citations AS jsonb))
                         || CAST(:extras AS jsonb))
                WHERE id = :node_id AND (model IS NULL OR model = :model_id) {guard}
            """),
            {
                "node_id": write_node_id,
                "user_text": user_text,
                "assistant_text": assistant_text,
                "model_id": model_id,
                "response_tokens": response_tokens,
                "citations": json.dumps(citations or []),
                "now": now,
                "author": author,
                "extras": json.dumps(extras or {}),
            },
        )
        if result.rowcount != 1:
            current_model = (
                await session.execute(
                    text("SELECT model FROM nodes WHERE id = :node_id"),
                    {"node_id": write_node_id},
                )
            ).scalar_one_or_none()
            if current_model is not None and current_model != model_id:
                raise NodeModelConflict(
                    f"This node is locked to model {current_model}; choose that model or create a new node."
                )
            raise RuntimeError(f"chat save matched {result.rowcount} rows for node {write_node_id}")


async def _create_child(
    db: AsyncSession,
    *,
    tree_id: UUID,
    project_id: UUID,
    parent_id: UUID,
    user_id: UUID,
    chats: Optional[list] = None,
) -> Node:
    for _ in range(3):  # two simultaneous forks race for the same index; the unique constraint picks the loser
        next_index = (
            await db.execute(
                select(func.coalesce(func.max(Node.fork_index), 0) + 1).where(Node.parent_id == parent_id)
            )
        ).scalar_one()
        child = Node(
            tree_id=tree_id,
            project_id=project_id,
            parent_id=parent_id,
            fork_index=next_index,
            created_by_id=user_id,
            **({"chats": chats} if chats else {}),
        )
        try:
            async with db.begin_nested():  # savepoint: a lost index race must not roll back a project fork
                db.add(child)
                await db.flush()
        except IntegrityError:
            continue
        return child
    raise HTTPException(409, "Could not allocate a branch slot; try again")


@router.get("/{node_id}", response_model=NodeOut)
async def get_node(
    node_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
):
    node = await db.get(Node, node_id)  # RLS: nodes of invisible projects are simply absent
    if node is None:
        raise HTTPException(404, "Node not found")
    await require_visible(db, node.project_id, user.id, node_id)
    return node


@router.post("/{node_id}/fork", response_model=ForkNodeOut)
async def fork_node(
    node_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
):
    """New empty child of any node (a "tangent"). fork_index is the next free sibling ordinal.
    A non-owner's first write forks the whole project; the child is created in their copy and the
    response carries `fork` (project id, slug, id maps) so the client can switch over."""
    parent = await db.get(Node, node_id)
    if parent is None:
        raise HTTPException(404, "Node not found")
    await require_visible(db, parent.project_id, user.id, node_id)

    parent_id, tree_id = parent.id, parent.tree_id
    project_id, fork = await get_write_target(db, parent.project_id, user.id)
    if fork is not None:
        parent_id = fork.node_map[parent_id]
        tree_id = fork.tree_map[tree_id]

    await resolving.reopen_for_work(db, parent_id, user.id)
    child = await _create_child(
        db, tree_id=tree_id, project_id=project_id, parent_id=parent_id, user_id=user.id
    )
    info = await build_fork_info(db, fork) if fork is not None else None
    await db.commit()
    await db.refresh(child)
    return ForkNodeOut(**NodeMeta.model_validate(child).model_dump(), fork=info)


class CompactOut(BaseModel):
    node: NodeMeta  # the new Compacted card
    fork: Optional[ForkInfo] = None


class ResolveIn(BaseModel):
    kind: Literal["resolved", "dead_lead", "off_topic"] = "resolved"  # resolving.ENDINGS


class ResolveOut(BaseModel):
    node: NodeMeta  # the card, stamped resolved (or no longer)
    fork: Optional[ForkInfo] = None


async def _write_card(db: AsyncSession, node_id: UUID, user_id: UUID) -> tuple[Node, Optional[ForkInfo]]:
    """The card a compact/resolve/reopen writes to: the node itself, or (a sharee's first write) its copy in their
    fork. 404 if invisible, 409 while a reply streams on it."""
    node = await db.get(Node, node_id)
    if node is None:
        raise HTTPException(404, "Node not found")
    await require_visible(db, node.project_id, user_id, node_id)
    _, fork = await get_write_target(db, node.project_id, user_id)
    if fork is not None:
        node = await db.get(Node, fork.node_map[node.id])
    # shortcut: _stops is in-process, so this only sees streams on this worker; same limit as split_node
    if any(streaming in (node_id, node.id) for _, streaming in _stops):
        raise HTTPException(409, "Wait for the reply to finish first")
    return node, (await build_fork_info(db, fork) if fork is not None else None)


@router.post("/{node_id}/compact", response_model=CompactOut)
async def compact_node(node_id: UUID, db: AsyncSession = Depends(get_db_session), user: User = Depends(get_current_user)):
    """The card's model summarises its thread into a new Compacted child: a fresh start below it."""
    node, info = await _write_card(db, node_id, user.id)
    card = await resolving.compact(db, node, user.id)
    await db.commit()
    await db.refresh(card)
    return CompactOut(node=NodeMeta.model_validate(card), fork=info)


@router.post("/{node_id}/resolve", response_model=ResolveOut)
async def resolve_node(node_id: UUID, body: Optional[ResolveIn] = None, db: AsyncSession = Depends(get_db_session),
                       user: User = Depends(get_current_user)):
    """Stamp how the card's branch ended (resolved, a dead lead, ...): a marker that it is settled."""
    node, info = await _write_card(db, node_id, user.id)
    node = await resolving.resolve(db, node, user.id, "user", (body or ResolveIn()).kind)
    await db.commit()
    await db.refresh(node)
    return ResolveOut(node=NodeMeta.model_validate(node), fork=info)


@router.post("/{node_id}/reopen", response_model=ResolveOut)
async def reopen_node(node_id: UUID, db: AsyncSession = Depends(get_db_session), user: User = Depends(get_current_user)):
    """Take the resolved stamp off."""
    node, info = await _write_card(db, node_id, user.id)
    await resolving.reopen(db, node, user.id)
    await db.commit()
    await db.refresh(node)
    return ResolveOut(node=NodeMeta.model_validate(node), fork=info)


_RESET_SQL = text("""
    WITH RECURSIVE doomed(id) AS (
      SELECT id FROM nodes WHERE parent_id = :root
      UNION
      SELECT e.child
      FROM doomed d
      JOIN (
        SELECT id AS child, parent_id AS parent FROM nodes WHERE parent_id IS NOT NULL
        UNION ALL
        SELECT node_id, source_leaf_id FROM node_merge_sources
      ) e ON e.parent = d.id
    )
    DELETE FROM nodes WHERE id IN (SELECT id FROM doomed) AND id <> :root
""")


class AnswerIn(BaseModel):
    answer: Union[str, list[str]]


class AnswerOut(BaseModel):
    node: NodeMeta  # the branch the answer opened (or had opened before)
    existing: bool  # answered this way before: the branch already existed
    final: bool  # the last question of its chain: `node` is where the research continues
    # a card's model asked: send this in `node` (with the card's model) to continue the research
    continue_prompt: Optional[str] = None
    fork: Optional[ForkInfo] = None


@router.post("/{node_id}/answer", response_model=AnswerOut)
async def answer_question(
    node_id: UUID,
    req: AnswerIn,
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
):
    """Answer a question card. A new answer opens a branch (the chain's next question, or after the last, the card
    where the research continues); the same answer again returns its branch. A running Gent hears about it."""
    card = await db.get(Node, node_id)
    if card is None:
        raise HTTPException(404, "Node not found")
    await require_visible(db, card.project_id, user.id, node_id)
    user_id = user.id
    project_id, fork = await get_write_target(db, card.project_id, user_id)
    if fork is not None:
        card = await db.get(Node, fork.node_map[card.id])
    await resolving.reopen_for_work(db, card.id, user_id)
    out = await questions.answer(db, card, user_id, req.answer)
    update = question_update(card, out, "user")
    info = await build_fork_info(db, fork) if fork is not None else None
    await db.commit()
    await db.refresh(out["node"])
    tell_gent(user_id, project_id, update)
    continues = out["final"] and not out["existing"] and out["asker"].get("by") == "node"
    return AnswerOut(node=NodeMeta.model_validate(out["node"]), existing=out["existing"], final=out["final"],
                     continue_prompt=questions.trail_text(out["trail"]) if continues else None, fork=info)


def question_update(card: Node, out: dict, by: str) -> dict:
    """What Gent hears when a question card is answered (read before commit: the rows expire)."""
    return {"kind": "question", "id": str(card.id), "chain": out["chain"], "question": card.question["prompt"],
            "answer": out["trail"][-1]["answer"], "branch": str(out["node"].id), "final": out["final"],
            "existing": out["existing"], "by": by, "asker": (out["asker"] or {}).get("by"),
            **({"trail": out["trail"]} if out["final"] else {})}


def tell_gent(user_id: UUID, project_id: UUID, update: dict) -> None:
    """A running Gent on this project hears about an answered question (it wakes his wait), and his log shows it."""
    from app.agent.router import _runs  # here: the agent imports this module

    run = _runs.get((user_id, project_id))
    if run is None:
        return
    run.post(update)
    run.emit("question_answered", {k: v for k, v in update.items() if k != "kind"})
    run.emit("tree", {})


@router.post("/{node_id}/reset", response_model=ForkNodeOut)
async def reset_project(
    node_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
):
    """Start the project over from its root: every branch goes (merges included) and the root's conversation, title
    and token count are cleared, leaving one blank card. Sources stay. A non-owner's reset is their first write, so
    it forks the project and resets their copy; the response carries `fork`, like fork_node."""
    root = await db.get(Node, node_id)
    if root is None:
        raise HTTPException(404, "Node not found")
    if root.parent_id is not None:
        raise HTTPException(409, "Only the root node resets the project")
    await require_visible(db, root.project_id, user.id, node_id)
    project_nodes = set((await db.execute(select(Node.id).where(Node.project_id == root.project_id))).scalars())
    # shortcut: _stops is in-process, so this only sees streams on this worker; same limit as split_node
    if any(streaming in project_nodes for _, streaming in _stops):
        raise HTTPException(409, "A reply is still streaming in this project; wait for it to finish")

    project_id, fork = await get_write_target(db, root.project_id, user.id)
    root_id = fork.node_map[node_id] if fork is not None else node_id
    info = await build_fork_info(db, fork) if fork is not None else None
    await db.execute(_RESET_SQL, {"root": root_id})
    await db.execute(
        text("""UPDATE nodes SET chats = '[]'::jsonb, title = NULL, summary = NULL, tokens = 0, model = NULL
                WHERE id = :root"""),
        {"root": root_id},
    )
    await db.commit()
    fresh = await db.get(Node, root_id)
    await db.refresh(fresh)
    return ForkNodeOut(**NodeMeta.model_validate(fresh).model_dump(), fork=info)


@router.post("/{node_id}/split", response_model=SplitOut)
async def split_node(
    node_id: UUID,
    req: SplitRequest,
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
):
    """Cut a node in two after one of its replies, so a long conversation can be branched from mid-way.
    The node keeps its messages up to and including that reply; a new child takes the rest (renumbered
    from 0) and every child the node had, so nothing below moves. With `tangent`, an empty sibling of that
    child is made too: a branch off the cut, ready to prompt. A non-owner's first write forks the project,
    exactly like fork_node, and the split happens in their copy."""
    node = await db.get(Node, node_id)
    if node is None:
        raise HTTPException(404, "Node not found")
    await require_visible(db, node.project_id, user.id, node_id)
    project_id, fork = await get_write_target(db, node.project_id, user.id)
    if fork is not None:
        node = await db.get(Node, fork.node_map[node.id])
    # locked, so a reply being saved can't land on either half mid-split
    node = (await db.execute(select(Node).where(Node.id == node.id).with_for_update())).scalar_one()
    # shortcut: _stops is in-process, so this only sees streams on this worker; same limit as stop_message
    if any(streaming == node_id or streaming == node.id for _, streaming in _stops):
        raise HTTPException(409, "Wait for the reply to finish before splitting")

    chats = _as_list(node.chats)
    if req.after_seq >= len(chats) - 1:
        raise HTTPException(400, "Nothing comes after that message; fork the node instead")
    if chats[req.after_seq].get("role") != "assistant":
        raise HTTPException(400, "A node can only be split after a reply")

    await resolving.reopen_for_work(db, node.id, user.id)
    head, rest = chats[: req.after_seq + 1], chats[req.after_seq + 1 :]
    rest = [{**m, "seq": i} for i, m in enumerate(rest)]
    first_question = next((m["content"] for m in rest if m.get("role") == "user"), None)

    node.chats = head
    tail = await _create_child(
        db, tree_id=node.tree_id, project_id=project_id, parent_id=node.id, user_id=user.id, chats=rest
    )
    tail.title = first_question[:40] if first_question else None
    # a merge whose source was this node took the conversation to its end, which now ends at the tail
    await db.execute(
        NodeMergeSource.__table__.update().where(NodeMergeSource.source_leaf_id == node.id).values(source_leaf_id=tail.id)
    )
    # its replies came from the node's model, so it's locked to the same one; the token count stays with the node
    tail.model = node.model
    await db.execute(
        Node.__table__.update()
        .where(Node.parent_id == node.id, Node.id != tail.id)
        .values(parent_id=tail.id)
    )
    tangent = (
        await _create_child(db, tree_id=node.tree_id, project_id=project_id, parent_id=node.id, user_id=user.id)
        if req.tangent
        else None
    )
    info = await build_fork_info(db, fork) if fork is not None else None
    await db.commit()
    for n in (node, tail, tangent):
        if n is not None:
            await db.refresh(n)
    return SplitOut(
        head=NodeMeta.model_validate(node),
        tail=NodeMeta.model_validate(tail),
        tangent=NodeMeta.model_validate(tangent) if tangent else None,
        fork=info,
    )


@router.post("/{node_id}/join", response_model=ForkNodeOut)
async def join_child(
    node_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
):
    """Fold a node's only child back into it: a split undone. The child's messages are appended (renumbered),
    its children move up to the node, and it is deleted. A non-owner's first write forks the project, as for fork."""
    node = await db.get(Node, node_id)
    if node is None:
        raise HTTPException(404, "Node not found")
    await require_visible(db, node.project_id, user.id, node_id)
    _, fork = await get_write_target(db, node.project_id, user.id)
    target_id = fork.node_map[node.id] if fork is not None else node.id
    node = (await db.execute(select(Node).where(Node.id == target_id).with_for_update())).scalar_one()
    children = (await db.execute(select(Node).where(Node.parent_id == node.id).with_for_update())).scalars().all()
    if len(children) != 1:
        raise HTTPException(409, "Only a node with exactly one branch can take it back in")
    child = children[0]
    child_is_merge = (
        await db.execute(select(NodeMergeSource.node_id).where(NodeMergeSource.node_id == child.id).limit(1))
    ).scalar_one_or_none()
    if child_is_merge is not None:
        raise HTTPException(409, "A merge can't be folded into one of its sources")
    node_feeds_merge = (
        await db.execute(
            select(NodeMergeSource.node_id).where(NodeMergeSource.source_leaf_id == node.id).limit(1)
        )
    ).scalar_one_or_none()
    if node_feeds_merge is not None:
        raise HTTPException(409, "A card that feeds a merge can't take its child back in")
    if any(streaming in (node_id, node.id, child.id) for _, streaming in _stops):
        raise HTTPException(409, "Wait for the reply to finish before merging")
    if node.model and child.model and node.model != child.model:
        raise HTTPException(409, "These two use different models, so they can't become one node")
    await resolving.reopen_for_work(db, node.id, user.id)
    node.model = node.model or child.model
    node.tokens += child.tokens

    node.chats = [{**m, "seq": i} for i, m in enumerate(_as_list(node.chats) + _as_list(child.chats))]
    # out of the way first: a grandchild moving up may hold the same fork_index under the node
    await db.execute(Node.__table__.update().where(Node.id == child.id).values(fork_index=-1))
    await db.execute(Node.__table__.update().where(Node.parent_id == child.id).values(parent_id=node.id))
    # A merge that came from the child now follows the conversation into the node.
    await db.execute(
        NodeMergeSource.__table__.update().where(NodeMergeSource.source_leaf_id == child.id).values(source_leaf_id=node.id)
    )
    # Core delete: the ORM's delete-orphan cascade must not reach the children that just moved
    await db.execute(Node.__table__.delete().where(Node.id == child.id))
    info = await build_fork_info(db, fork) if fork is not None else None
    await db.commit()
    await db.refresh(node)
    return ForkNodeOut(**NodeMeta.model_validate(node).model_dump(), fork=info)


@router.post("/merge", response_model=ForkNodeOut)
async def merge_nodes(
    req: MergeRequest,
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
):
    """Create a merge node from two or more leaves. A non-owner's first write forks the project."""
    source_ids = req.source_leaf_ids
    if len(set(source_ids)) != len(source_ids):
        raise HTTPException(400, "Pick different leaf nodes")

    locked_nodes = (
        await db.execute(
            select(Node)
            .where(Node.id.in_(source_ids))
            .order_by(Node.id)
            .with_for_update()
        )
    ).scalars().all()
    if len(locked_nodes) != len(source_ids):
        raise HTTPException(404, "Node not found")
    if len({n.tree_id for n in locked_nodes}) != 1 or len({n.project_id for n in locked_nodes}) != 1:
        raise HTTPException(400, "All nodes must be in the same tree")
    tree_id, project_id = locked_nodes[0].tree_id, locked_nodes[0].project_id
    await require_visible(db, project_id, user.id, *source_ids)

    linked_sources = (
        await db.execute(
            select(Node.id)
            .where(
                or_(
                    Node.parent_id.in_(source_ids),
                    Node.id.in_(
                        select(NodeMergeSource.node_id).where(NodeMergeSource.source_leaf_id.in_(source_ids))
                    ),
                )
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if linked_sources is not None:
        raise HTTPException(409, "Only cards at the ends of their branches can be merged")
    if any(
        (user.id, source_id) in _stops
        for source_id in [*source_ids, *(n.id for n in locked_nodes)]
    ):
        raise HTTPException(409, "Wait for the reply to finish before merging")

    project_id, fork = await get_write_target(db, project_id, user.id)
    if fork is not None:
        tree_id = fork.tree_map[tree_id]
        source_ids = [fork.node_map[source_id] for source_id in source_ids]

    for source_id in source_ids:
        await resolving.reopen_for_work(db, source_id, user.id)
    child = await _create_child(
        db, tree_id=tree_id, project_id=project_id, parent_id=source_ids[0], user_id=user.id
    )
    for source_id in source_ids:
        db.add(NodeMergeSource(node_id=child.id, source_leaf_id=source_id))
    await db.flush()

    info = await build_fork_info(db, fork) if fork is not None else None
    await db.commit()
    await db.refresh(child)
    meta = NodeMeta.model_validate(child).model_copy(update={"merge_source_ids": source_ids})
    return ForkNodeOut(**meta.model_dump(), fork=info)


@router.post("/{node_id}/messages/stop", status_code=204)
async def stop_message(node_id: UUID, user: User = Depends(get_current_user)):
    """Stop the caller's reply streaming on this node. What arrived so far is saved, and the stream ends with
    `done {stopped: true}`. A no-op when nothing is streaming (it already finished, or never started)."""
    stop = _stops.get((user.id, node_id))
    if stop is not None:
        stop.set()


@router.delete("/{node_id}", status_code=204)
async def delete_node(
    node_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
):
    """Delete a node and every descendant that depends on it through either parent link."""
    node = await db.get(Node, node_id)
    if node is None:
        raise HTTPException(404, "Node not found")
    owner_id = (await db.execute(select(Project.created_by_id).where(Project.id == node.project_id))).scalar_one()
    if owner_id != user.id:
        raise HTTPException(403, "Only the project owner can delete")
    if node.parent_id is None:
        raise HTTPException(409, "The root node can't be deleted")
    await db.execute(
        text("""
            WITH RECURSIVE doomed(id) AS (
              SELECT CAST(:node_id AS uuid)
              UNION
              SELECT e.child
              FROM doomed d
              JOIN (
                SELECT id AS child, parent_id AS parent FROM nodes WHERE parent_id IS NOT NULL
                UNION ALL
                SELECT node_id, source_leaf_id FROM node_merge_sources
              ) e ON e.parent = d.id
            )
            DELETE FROM nodes WHERE id IN (SELECT id FROM doomed)
        """),
        {"node_id": node_id},
    )
    await db.commit()


async def node_messages(
    db: AsyncSession, node_id: UUID, user_id: UUID, prompt: str, model: str, retry: bool = False
) -> tuple[list[dict], UUID, str]:
    """What the provider is sent to prompt a leaf: the research system prompt, the sources note and the node's
    whole ancestry (merges included). 404/409 like send_message. Returns (messages, project id, prompt asked)."""
    get_model_or_400(model)
    path, project_id = await _load_path(db, node_id, user_id)
    if path[-1].model is not None and path[-1].model != model:
        raise HTTPException(
            409,
            f"This node is locked to model {path[-1].model}; choose that model or create a new node.",
        )
    if retry:
        chats = path[-1].chats
        if len(chats) < 2 or chats[-2].role != "user" or chats[-1].role != "assistant":
            raise HTTPException(409, "There's no reply on this node to retry")
        # the stored question, not the client's copy: a retry re-asks exactly what was asked
        prompt = chats[-2].content
        path[-1] = path[-1].model_copy(update={"chats": chats[:-2]})
    nodes = {node.id: node for node in path}
    # a Compacted card on the thread is a fresh start: its summary stands in for everything above it
    plan = resolving.thread_plan(path, str(node_id))
    system = (paper_service.RESEARCH_SYSTEM_PROMPT + paper_service.today_note()
              + await _sources_note(project_id, node_id))
    messages = [{"role": "system", "content": system}] + to_provider_messages(flatten(plan, nodes), prompt)
    return messages, project_id, prompt


def _error(payload: dict, fork: Optional[dict]) -> tuple[str, dict]:
    return "error", ({**payload, "fork": fork} if fork else payload)


async def answer_in_node(
    user_id: UUID,
    project_id: UUID,
    node_id: UUID,
    messages: list[dict],
    prompt: str,
    model: str,
    emit,
    retry: bool = False,
    author: str = "user",
) -> dict:
    """The whole write pipeline for one prompt to a leaf: fork (sharee) -> research tool loop -> save.
    emit(event, data) receives `token`, `tool`, `reasoning`, `question` (a question card was made under this one),
    then `done` or `error`: exactly what send_message streams.
    Shared with Gent, so his questions get the same research a user's do; `author` records who asked. Never raises.
    Returns {"answer", "error", "fork", "stopped"}; answer is the saved reply, "" when nothing was saved."""
    outcome: dict = {"answer": "", "error": None, "fork": None, "stopped": False, "question": None}

    def note(event: str, data: dict) -> None:
        if event == "error":
            outcome["error"] = data.get("message") or "The reply failed."
        emit(event, data)

    await _answer(user_id, project_id, node_id, messages, prompt, model, note, retry, outcome, author)
    return outcome


async def _answer(user_id, project_id, node_id, messages, prompt, model, emit, retry, outcome, author) -> None:
    fork: Optional[dict] = None
    # registered first, so a stop sent while the project is still being copied isn't lost
    key = (user_id, node_id)
    stop = _stops[key] = asyncio.Event()
    try:
        try:
            write_node_id, fork = await _prepare_write(user_id, project_id, node_id)
            outcome["fork"] = fork
        except HTTPException as exc:
            detail = exc.detail if isinstance(exc.detail, dict) else {"message": exc.detail}
            emit("error", detail)
            return
        except Exception:
            log.exception("forking project %s for user %s failed", project_id, user_id)
            emit("error", {"message": "The project could not be copied."})
            return
        if reopened := await _reopen_for_work(user_id, write_node_id):
            emit("reopened", {"ids": reopened})

        reply: list[str] = []
        done: dict = {}
        evidence: dict[str, dict] = {}  # PDF evidence ids the tools returned this turn -> {title, section, pages}
        web_evidence: dict[str, dict] = {}  # web citation ids ("web:1") the tools returned this turn -> source
        rows: list[dict] = []  # the tool calls, as the chat shows them
        thought = {"text": "", "seconds": 0.0}
        try:
            reasons = get_model_or_400(model).supports_reasoning
        except HTTPException:
            reasons = False

        kept = {"from": 0}  # where the answer starts in `reply`: after the text of the last round that called tools

        async def pump() -> Optional[str]:
            """Relay the provider's tokens, running research tools when it calls them (bounded by
            MAX_TOOL_ROUNDS); returns its error message, or None once it finishes."""
            convo = list(messages)
            retried = False
            urged = False  # sent "answer now" once after a round that ended with nothing to show
            pushed = False  # sent back NOT_AN_ANSWER once
            round_no = 0
            think = False  # the last round called think(): this one reasons first
            while round_no <= MAX_TOOL_ROUNDS:
                calls, said = None, len(reply)
                last = round_no == MAX_TOOL_ROUNDS
                if last and not urged:
                    # told only by tool_choice, these models write nothing at all: the answer must be asked for in words
                    urged = True
                    convo.append({"role": "user", "content": ANSWER_NOW})
                held, mode = "", None  # mode: None = undecided, "stream", or "hold" (a tool call written as text)
                failed = None
                details = None
                started, thinking = asyncio.get_running_loop().time(), think
                async for ev in stream_openrouter(
                    convo, model, tools=NODE_TOOLS, tool_choice="none" if last else None,
                    reasoning={"effort": "low"} if think and reasons else None,
                ):
                    if "error" in ev:
                        failed = ev["error"]
                        break
                    if thinking and ("text" in ev or "tool_calls" in ev):
                        thinking = False  # done reasoning: the time it took is the "Thought for"
                        thought["seconds"] += asyncio.get_running_loop().time() - started
                    if "reasoning" in ev:
                        thought["text"] += ev["reasoning"]
                        emit("reasoning", {"text": ev["reasoning"]})
                    elif "reasoning_details" in ev:
                        details = ev["reasoning_details"]
                    elif "text" in ev:
                        if mode == "stream":
                            reply.append(ev["text"])
                            emit("token", {"text": ev["text"]})
                            continue
                        # decide from the first characters whether this reply is really a tool call in text
                        held += ev["text"]
                        if mode == "hold":
                            continue
                        head, marker = held.lstrip(), paper_service.LEAK_MARKER
                        if marker.startswith(head) and len(head) < len(marker):
                            continue  # still could be the marker
                        if head.startswith(marker):
                            mode = "hold"
                            continue
                        mode = "stream"
                        reply.append(held)
                        emit("token", {"text": held})
                    elif "tool_calls" in ev:
                        calls = ev["tool_calls"]
                    else:
                        done.update(ev)
                if failed is not None:
                    transient = isinstance(failed, dict) and type(failed.get("code")) is int and failed["code"] >= 500
                    if transient and not retried and len(reply) == said:
                        retried = True  # a provider hiccup before anything was shown: ask again once
                        continue
                    if isinstance(failed, dict):
                        return f"The model provider failed ({failed.get('message') or 'unknown error'}). Try again."
                    return failed
                if mode is None and held:  # a short reply that never reached the marker's length
                    reply.append(held)
                    emit("token", {"text": held})
                elif mode == "hold":
                    calls = paper_service.parse_leaked_tool_calls(held)
                    if not calls:  # it only looked like one: show it
                        reply.append(held)
                        emit("token", {"text": held})
                if thinking:
                    thought["seconds"] += asyncio.get_running_loop().time() - started
                if (not calls or last) and not "".join(reply[said:]).strip() and not urged:
                    # a turn that ends with nothing new (only reasoning, or only the "let me search" it wrote before
                    # its tool calls): go straight to the final round, which asks for the answer in words
                    round_no = MAX_TOOL_ROUNDS
                    continue
                if not calls and not last and not pushed and _non_answer("".join(reply[said:])):
                    pushed = True  # it echoed the question as "Open: …": send it back once to do the research
                    convo += [{"role": "assistant", "content": "".join(reply[said:])},
                              {"role": "user", "content": NOT_AN_ANSWER}]
                    kept["from"] = len(reply)
                    round_no += 1
                    continue
                if not calls or last:
                    return None
                round_no += 1
                kept["from"] = len(reply)  # what it wrote before these calls ("let me search…") isn't the answer
                turn = {"role": "assistant", "content": "".join(reply[said:]) or None, "tool_calls": calls}
                if details:
                    turn["reasoning_details"] = details  # sent back, as the provider requires
                convo.append(turn)
                think = False
                for i, call in enumerate(calls):
                    name = call["function"]["name"]
                    if i >= MAX_CALLS_PER_ROUND:  # every call still needs a reply, or the provider rejects the turn
                        result = {"error": f"At most {MAX_CALLS_PER_ROUND} tool calls at once; this one was skipped."}
                    elif name == "think":
                        think = True
                        result = {"ok": "Reason it through, then answer." if reasons
                                  else "Reason step by step in your reply before you answer."}
                    elif name == "ask_user":
                        result = await _ask_user(user_id, write_node_id, call, model)
                        if "card" in result:
                            outcome["question"] = result["card"]
                            emit("question", {"id": result["card"]})  # a new card on the map: the client re-reads it
                            round_no = MAX_TOOL_ROUNDS  # the next round is the last: it only says what was asked
                    else:
                        result = await _run_tool(call, project_id, node_id)
                    if i < MAX_CALLS_PER_ROUND:
                        try:
                            args = json.loads(call["function"]["arguments"] or "{}")
                        except ValueError:
                            args = {}
                        row = _tool_row(name, args if isinstance(args, dict) else {}, result)
                        if "card" in result:
                            row["node_id"] = result["card"]  # the question card it made: the client shows it
                        rows.append(row)
                        emit("tool", row)
                    if name == "web_search":  # number the results so the reply can cite them as [web:1]
                        numbered = []
                        for item in result.get("results") or []:
                            citation_id = f"web:{len(web_evidence) + 1}"
                            web_evidence[citation_id] = {
                                "title": item.get("title"), "url": item.get("url"),
                                **({"source": item["source"]} if item.get("source") else {}),
                                **({"date": item["date"]} if item.get("date") else {}),
                            }
                            numbered.append({**item, "citation_id": citation_id})
                        result = {**result, "results": numbered}
                    for ev in result.get("evidence") or []:
                        evidence[ev["evidence_id"]] = {"title": ev.get("title") or result.get("title"),
                                                       "section": ev.get("section"), "pages": ev["pages"]}
                    convo.append({"role": "tool", "tool_call_id": call["id"], "content": json.dumps(result)})
            return None

        # Race the provider against a stop: stopping cancels it at once, even before its first token.
        pumping = asyncio.create_task(pump())
        stopping = asyncio.create_task(stop.wait())
        try:
            await asyncio.wait({pumping, stopping}, return_when=asyncio.FIRST_COMPLETED)
        finally:
            stopping.cancel()
        stopped = not pumping.done()
        if stopped:
            pumping.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await pumping
            done = {"stopped": True}
            outcome["stopped"] = True
        else:
            try:
                err = pumping.result()
            except (httpx.HTTPError, ValueError):
                emit(*_error({"message": "The model provider failed; nothing was saved."}, fork))
                return
            if err is not None:
                emit(*_error({"message": err}, fork))
                return

        answer = _DATE_STAMP.sub("", "".join(reply[kept["from"]:]).strip() or "".join(reply))
        if answer != "".join(reply):
            done["content"] = answer  # the client shows what was saved, not the preamble it streamed
        if not answer and stopped:
            # stopped before the first token: nothing to keep, and the prompt goes unsaved with it
            emit("done", {**done, "fork": fork} if fork else done)
            return
        if not answer:
            emit(*_error({"message": "The model returned an empty reply; nothing was saved."}, fork))
            return
        if _non_answer(answer):
            emit(*_error({"message": "The model only restated the question instead of answering; nothing was saved."}, fork))
            return
        cited = paper_service.citations_in(answer)
        web_cited = paper_service.web_citations_in(answer)
        citations = [{"evidence_id": e, **evidence[e]} for e in cited if e in evidence] + \
            [{"evidence_id": e, "kind": "web", **web_evidence[e]} for e in web_cited if e in web_evidence]
        if cited or web_cited:
            # the stream's copy is lighter than the saved one: a PDF citation's title and pages, no section
            done["citations"] = [{k: v for k, v in c.items() if k != "section"} if c.get("kind") != "web" else c
                                 for c in citations]
            unverified = [e for e in cited if e not in evidence] + [e for e in web_cited if e not in web_evidence]
            if unverified:
                # the model cited passages no tool gave it this turn: flag them rather than vouch for them
                log.warning("node %s: reply cites evidence no tool returned: %s", write_node_id, unverified)
                done["unverified_citations"] = unverified
        usage = done.get("usage")
        response_tokens: Optional[int] = None
        if usage is not None:
            total_tokens = usage.get("total_tokens") if isinstance(usage, dict) else None
            if type(total_tokens) is int and total_tokens >= 0:
                response_tokens = total_tokens
            else:
                log.warning("Provider returned invalid token usage for node %s", write_node_id)
        try:
            await _persist(
                user_id,
                write_node_id,
                prompt,
                answer,
                model_id=model,
                response_tokens=response_tokens,
                replace_last=retry,
                citations=citations,
                author=author,
                extras={**({"tools": rows} if rows else {}),
                        **({"reasoning": thought["text"]} if thought["text"] else {}),
                        **({"thought_seconds": round(thought["seconds"])} if thought["seconds"] >= 1 else {})},
            )
        except NodeModelConflict as exc:
            log.warning("model conflict while saving reply to node %s", write_node_id)
            emit(*_error({"message": str(exc)}, fork))
            return
        except Exception:
            log.exception("saving chat to node %s failed", write_node_id)
            emit(*_error({"message": "The reply could not be saved."}, fork))
            return
        outcome["answer"] = answer
        emit("done", {**done, "fork": fork} if fork else done)
    except Exception:
        log.exception("chat pipeline for node %s crashed", node_id)
        emit(*_error({"message": "Something went wrong; the reply may not have been saved."}, fork))
    finally:
        if _stops.get(key) is stop:
            del _stops[key]


@router.post("/{node_id}/messages")
async def send_message(
    node_id: UUID,
    req: MessageRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Prompt a leaf node; stream the reply as SSE `token {text}`, then `done` or `error {message}`.
    The server rebuilds the history from the tree; the client sends only the new message.
    A non-owner reads the original; before the model is called the project is forked for them (committed on
    its own) and the reply is saved into the copy. `done` (or `error`, if the model fails after the fork) carries
    `fork`. The pipeline runs detached from the request, so closing the tab does not lose the reply or the fork."""
    messages, project_id, prompt = await node_messages(db, node_id, user.id, req.content, req.model, req.retry)
    user_id = user.id
    await db.rollback()  # release the connection for the length of the stream; only plain values are used below

    async def run(queue: "asyncio.Queue[Optional[str]]") -> None:
        try:
            await answer_in_node(
                user_id, project_id, node_id, messages, prompt, req.model,
                lambda event, data: queue.put_nowait(_sse(event, data)), retry=req.retry,
            )
        finally:
            queue.put_nowait(None)

    async def events():
        queue: asyncio.Queue = asyncio.Queue()
        task = asyncio.create_task(run(queue))
        _background_tasks.add(task)  # strong reference: the loop only keeps weak ones
        task.add_done_callback(_background_tasks.discard)
        while True:
            item = await queue.get()
            if item is None:
                return
            yield item

    # no-transform stops Next's /api rewrite from gzip-buffering the stream; X-Accel-Buffering does the same for nginx.
    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )
