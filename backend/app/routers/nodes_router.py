import asyncio
import contextlib
import json
import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

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

# Root -> leaf, one query (see context/flatten.py). Runs under the caller's RLS identity, so a node
# in a project the user cannot see comes back empty, exactly like a node that does not exist.
_PATH_SQL = text("""
    WITH RECURSIVE path AS (
      SELECT id, parent_id, chats, model, 0 AS depth FROM nodes WHERE id = :node_id
      UNION ALL
      SELECT n.id, n.parent_id, n.chats, n.model, p.depth + 1
      FROM nodes n JOIN path p ON n.id = p.parent_id
    )
    SELECT id::text AS id, chats, model FROM path ORDER BY depth DESC
""")


class MessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=20_000)
    model: str = DEFAULT_MODEL_ID
    # Regenerate the node's last reply: its last question is asked again and the new exchange replaces the old one.
    retry: bool = False


class MergeRequest(BaseModel):
    source_leaf_ids: list[UUID] = Field(min_length=2, max_length=2)


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
MAX_CALLS_PER_ROUND = 5
TOOL_TIMEOUT = 30  # seconds per tool call; search_paper_evidence waits up to 25 for a PDF


async def _run_tool(call: dict, project_id: UUID) -> dict:
    """One tool call from the model -> its result. Failures become results the model can read, not errors."""
    name = call["function"]["name"]
    try:
        args = json.loads(call["function"]["arguments"] or "{}")
    except ValueError:
        return {"error": "The tool arguments were not valid JSON."}
    try:
        return await asyncio.wait_for(paper_service.call_tool(name, args, project_id), TOOL_TIMEOUT)
    except asyncio.TimeoutError:
        log.warning("tool %s timed out", name)
        return {"error": "The tool timed out; continue without it and say so."}


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _as_list(chats) -> list[dict]:
    return json.loads(chats) if isinstance(chats, str) else list(chats or [])


async def _load_path(
    db: AsyncSession, node_id: UUID, user_id: UUID
) -> tuple[list[PathNode], UUID]:
    rows = (await db.execute(_PATH_SQL, {"node_id": node_id})).all()
    if not rows:
        raise HTTPException(404, "Node not found")
    flags = (
        await db.execute(
            text("""
                SELECT n.project_id AS project_id,
                       p.created_by_id AS owner_id,
                       EXISTS (SELECT 1 FROM nodes c WHERE c.parent_id = n.id) AS has_child
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
    return [PathNode(id=r.id, chats=r.chats, model=getattr(r, "model", None)) for r in rows], flags.project_id


_background_tasks: set = set()


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
    replace_last: bool = False,
) -> None:
    """Append the exchange to nodes.chats of the node already resolved by _prepare_write. Own session: the
    request's may already be closed once the stream ends. `||` appends atomically (no read-modify-write);
    seq is the new array index. The node's model is set once; only provider-reported usage is added."""
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
                         'role', 'user', 'content', CAST(:user_text AS text),
                         'seq', jsonb_array_length({base}), 'branch_source', NULL, 'created_at', CAST(:now AS text)))
                    || jsonb_build_array(jsonb_build_object(
                         'role', 'assistant', 'content', CAST(:assistant_text AS text),
                         'seq', jsonb_array_length({base}) + 1, 'branch_source', NULL, 'created_at', CAST(:now AS text)))
                WHERE id = :node_id AND (model IS NULL OR model = :model_id) {guard}
            """),
            {
                "node_id": write_node_id,
                "user_text": user_text,
                "assistant_text": assistant_text,
                "model_id": model_id,
                "response_tokens": response_tokens,
                "now": now,
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

    child = await _create_child(
        db, tree_id=tree_id, project_id=project_id, parent_id=parent_id, user_id=user.id
    )
    info = await build_fork_info(db, fork) if fork is not None else None
    await db.commit()
    await db.refresh(child)
    return ForkNodeOut(**NodeMeta.model_validate(child).model_dump(), fork=info)


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
    if any(streaming in (node_id, node.id, child.id) for _, streaming in _stops):
        raise HTTPException(409, "Wait for the reply to finish before merging")
    if node.model and child.model and node.model != child.model:
        raise HTTPException(409, "These two use different models, so they can't become one node")
    node.model = node.model or child.model
    node.tokens += child.tokens

    node.chats = [{**m, "seq": i} for i, m in enumerate(_as_list(node.chats) + _as_list(child.chats))]
    # out of the way first: a grandchild moving up may hold the same fork_index under the node
    await db.execute(Node.__table__.update().where(Node.id == child.id).values(fork_index=-1))
    await db.execute(Node.__table__.update().where(Node.parent_id == child.id).values(parent_id=node.id))
    # merges that came from the child, or that the child is, are the node's now: deleting it would drop them
    await db.execute(
        NodeMergeSource.__table__.update().where(NodeMergeSource.source_leaf_id == child.id).values(source_leaf_id=node.id)
    )
    await db.execute(NodeMergeSource.__table__.update().where(NodeMergeSource.node_id == child.id).values(node_id=node.id))
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
    """Merge two leaves of one tree into a new node. The new node hangs off the nearest common ancestor and
    carries both branches (everything below that ancestor) in its own chats, tagged with branch_source = the
    source leaf id, so the merge never needs to walk its sources. node_merge_sources records the two leaves.
    A non-owner's first write forks the project, exactly like fork_node."""
    a_id, b_id = req.source_leaf_ids
    if a_id == b_id:
        raise HTTPException(400, "Pick two different leaf nodes")

    metas = (
        await db.execute(
            select(Node.id, Node.tree_id, Node.project_id).where(Node.id.in_([a_id, b_id]))
        )
    ).all()
    if len(metas) != 2:
        raise HTTPException(404, "Node not found")
    if len({m.tree_id for m in metas}) != 1 or len({m.project_id for m in metas}) != 1:
        raise HTTPException(400, "Both nodes must be in the same tree")
    tree_id, project_id = metas[0].tree_id, metas[0].project_id
    await require_visible(db, project_id, user.id, a_id, b_id)

    has_child = (
        await db.execute(select(Node.id).where(Node.parent_id.in_([a_id, b_id])).limit(1))
    ).scalar_one_or_none()
    if has_child is not None:
        raise HTTPException(409, "Only leaf nodes can be merged")

    path_a = (await db.execute(_PATH_SQL, {"node_id": a_id})).all()
    path_b = (await db.execute(_PATH_SQL, {"node_id": b_id})).all()
    shared = 0
    while shared < min(len(path_a), len(path_b)) and path_a[shared].id == path_b[shared].id:
        shared += 1
    if shared == 0:
        raise HTTPException(400, "Both nodes must be in the same tree")
    ancestor_id = UUID(path_a[shared - 1].id)

    chats: list[dict] = []
    # tagged "a" / "b" by branch, which is what ChatMessage and flatten() read
    for key, rows in (("a", path_a), ("b", path_b)):
        for row in rows[shared:]:
            for message in _as_list(row.chats):
                chats.append({**message, "branch_source": key})
    for seq, message in enumerate(chats):
        message["seq"] = seq

    sources = [a_id, b_id]
    project_id, fork = await get_write_target(db, project_id, user.id)
    if fork is not None:
        tree_id = fork.tree_map[tree_id]
        ancestor_id = fork.node_map[ancestor_id]
        sources = [fork.node_map[s] for s in sources]

    child = await _create_child(
        db, tree_id=tree_id, project_id=project_id, parent_id=ancestor_id, user_id=user.id, chats=chats
    )
    for source_id in sources:
        db.add(NodeMergeSource(node_id=child.id, source_leaf_id=source_id))
    await db.flush()

    info = await build_fork_info(db, fork) if fork is not None else None
    await db.commit()
    await db.refresh(child)
    return ForkNodeOut(**NodeMeta.model_validate(child).model_dump(), fork=info)


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
    """Delete a node and every branch under it (nodes.parent_id cascades). The root stays: a tree needs one."""
    node = await db.get(Node, node_id)
    if node is None:
        raise HTTPException(404, "Node not found")
    owner_id = (await db.execute(select(Project.created_by_id).where(Project.id == node.project_id))).scalar_one()
    if owner_id != user.id:
        raise HTTPException(403, "Only the project owner can delete")
    if node.parent_id is None:
        raise HTTPException(409, "The root node can't be deleted")
    await db.delete(node)
    await db.commit()


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
    get_model_or_400(req.model)
    path, project_id = await _load_path(db, node_id, user.id)
    if path[-1].model is not None and path[-1].model != req.model:
        raise HTTPException(
            409,
            f"This node is locked to model {path[-1].model}; choose that model or create a new node.",
        )
    prompt = req.content
    if req.retry:
        chats = path[-1].chats
        if len(chats) < 2 or chats[-2].role != "user" or chats[-1].role != "assistant":
            raise HTTPException(409, "There's no reply on this node to retry")
        # the stored question, not the client's copy: a retry re-asks exactly what was asked
        prompt = chats[-2].content
        path[-1] = path[-1].model_copy(update={"chats": chats[:-2]})
    system = paper_service.RESEARCH_SYSTEM_PROMPT + await paper_service.project_sources_note(project_id)
    messages = [{"role": "system", "content": system}] + to_provider_messages(flatten(path), prompt)
    user_id = user.id
    await db.rollback()  # release the connection for the length of the stream; only plain values are used below

    def _error(payload: dict, fork: Optional[dict]) -> str:
        return _sse("error", {**payload, "fork": fork} if fork else payload)

    async def run(queue: "asyncio.Queue[Optional[str]]") -> None:
        """The whole write pipeline, detached from the HTTP request: fork (sharee) -> stream -> save.
        It keeps going if the client disconnects, so a closed tab neither loses the reply nor the fork."""
        fork: Optional[dict] = None
        # registered first, so a stop sent while the project is still being copied isn't lost
        key = (user_id, node_id)
        stop = _stops[key] = asyncio.Event()
        try:
            try:
                write_node_id, fork = await _prepare_write(user_id, project_id, node_id)
            except HTTPException as exc:
                detail = exc.detail if isinstance(exc.detail, dict) else {"message": exc.detail}
                queue.put_nowait(_sse("error", detail))
                return
            except Exception:
                log.exception("forking project %s for user %s failed", project_id, user_id)
                queue.put_nowait(_sse("error", {"message": "The project could not be copied."}))
                return

            reply: list[str] = []
            done: dict = {}
            evidence: dict[str, dict] = {}  # evidence ids the tools returned this turn -> {title, pages}

            async def pump() -> Optional[str]:
                """Relay the provider's tokens, running research tools when it calls them (bounded by
                MAX_TOOL_ROUNDS); returns its error message, or None once it finishes."""
                convo = list(messages)
                for round_no in range(MAX_TOOL_ROUNDS + 1):
                    calls, said = None, len(reply)
                    last = round_no == MAX_TOOL_ROUNDS
                    async for ev in stream_openrouter(
                        convo, req.model, tools=paper_service.TOOLS, tool_choice="none" if last else None
                    ):
                        if "error" in ev:
                            err = ev["error"]
                            return err if isinstance(err, str) else json.dumps(err)
                        if "text" in ev:
                            reply.append(ev["text"])
                            queue.put_nowait(_sse("token", {"text": ev["text"]}))
                        elif "tool_calls" in ev:
                            calls = ev["tool_calls"]
                        else:
                            done.update(ev)
                    if not calls or last:
                        return None
                    convo.append({"role": "assistant", "content": "".join(reply[said:]) or None, "tool_calls": calls})
                    for i, call in enumerate(calls):
                        if i >= MAX_CALLS_PER_ROUND:  # every call still needs a reply, or the provider rejects the turn
                            result = {"error": f"At most {MAX_CALLS_PER_ROUND} tool calls at once; this one was skipped."}
                        else:
                            queue.put_nowait(_sse("tool", {"name": call["function"]["name"]}))
                            result = await _run_tool(call, project_id)
                        for ev in result.get("evidence") or []:
                            evidence[ev["evidence_id"]] = {"title": result.get("title"), "pages": ev["pages"]}
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
            else:
                try:
                    err = pumping.result()
                except (httpx.HTTPError, ValueError):
                    queue.put_nowait(_error({"message": "The model provider failed; nothing was saved."}, fork))
                    return
                if err is not None:
                    queue.put_nowait(_error({"message": err}, fork))
                    return

            answer = "".join(reply)
            if not answer and stopped:
                # stopped before the first token: nothing to keep, and the prompt goes unsaved with it
                queue.put_nowait(_sse("done", {**done, "fork": fork} if fork else done))
                return
            if not answer:
                queue.put_nowait(_error({"message": "The model returned an empty reply; nothing was saved."}, fork))
                return
            cited = paper_service.citations_in(answer)
            if cited:
                done["citations"] = [{"evidence_id": e, **evidence[e]} for e in cited if e in evidence]
                unverified = [e for e in cited if e not in evidence]
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
                    model_id=req.model,
                    response_tokens=response_tokens,
                    replace_last=req.retry,
                )
            except NodeModelConflict as exc:
                log.warning("model conflict while saving reply to node %s", write_node_id)
                queue.put_nowait(_error({"message": str(exc)}, fork))
                return
            except Exception:
                log.exception("saving chat to node %s failed", write_node_id)
                queue.put_nowait(_error({"message": "The reply could not be saved."}, fork))
                return
            queue.put_nowait(_sse("done", {**done, "fork": fork} if fork else done))
        except Exception:
            log.exception("chat pipeline for node %s crashed", node_id)
            queue.put_nowait(_error({"message": "Something went wrong; the reply may not have been saved."}, fork))
        finally:
            if _stops.get(key) is stop:
                del _stops[key]
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