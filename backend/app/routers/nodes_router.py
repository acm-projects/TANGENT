import asyncio
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
from app.context.flatten import flatten, to_provider_messages
from app.context.schemas import NodeMeta, NodeOut, PathNode
from app.core.openrouter import DEFAULT_MODEL_ID, get_model_or_400, stream_openrouter
from app.database import AsyncSessionLocal, get_db_session
from app.models import Node, NodeMergeSource, Project, User
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
      SELECT id, parent_id, chats, 0 AS depth FROM nodes WHERE id = :node_id
      UNION ALL
      SELECT n.id, n.parent_id, n.chats, p.depth + 1
      FROM nodes n JOIN path p ON n.id = p.parent_id
    )
    SELECT id::text AS id, chats FROM path ORDER BY depth DESC
""")


class MessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=20_000)
    model: str = DEFAULT_MODEL_ID


class MergeRequest(BaseModel):
    source_leaf_ids: list[UUID] = Field(min_length=2, max_length=2)


class ForkNodeOut(NodeMeta):
    fork: Optional[ForkInfo] = None


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
    return [PathNode(id=r.id, chats=r.chats) for r in rows], flags.project_id


_background_tasks: set = set()


async def _prepare_write(user_id: UUID, project_id: UUID, node_id: UUID) -> tuple[UUID, Optional[dict]]:
    """Resolve where this write goes. Owner: the node itself. Sharee: fork the project first (own session,
    committed on its own so the copy exists whatever happens to the model call) and map the node into the copy.
    Returns (node id to write to, fork payload for the client or None)."""
    async with AsyncSessionLocal() as session, session.begin():
        await session.execute(
            text("SELECT set_config('app.current_user_id', :uid, true)"), {"uid": str(user_id)}
        )
        _, fork = await get_write_target(session, project_id, user_id)
        if fork is None:
            return node_id, None
        info = await build_fork_info(session, fork)
        write_node_id = fork.node_map[node_id]
        return write_node_id, {**info.model_dump(mode="json"), "node_id": str(write_node_id)}


async def _persist(user_id: UUID, write_node_id: UUID, user_text: str, assistant_text: str) -> None:
    """Append the exchange to nodes.chats of the node already resolved by _prepare_write. Own session: the
    request's may already be closed once the stream ends. `||` appends atomically (no read-modify-write);
    seq is the new array index."""
    now = datetime.now(timezone.utc).isoformat()
    async with AsyncSessionLocal() as session, session.begin():
        await session.execute(
            text("SELECT set_config('app.current_user_id', :uid, true)"), {"uid": str(user_id)}
        )
        result = await session.execute(
            text("""
                UPDATE nodes SET
                  title = COALESCE(title, left(CAST(:user_text AS text), 40)),
                  chats = chats
                    || jsonb_build_array(jsonb_build_object(
                         'role', 'user', 'content', CAST(:user_text AS text),
                         'seq', jsonb_array_length(chats), 'branch_source', NULL, 'created_at', CAST(:now AS text)))
                    || jsonb_build_array(jsonb_build_object(
                         'role', 'assistant', 'content', CAST(:assistant_text AS text),
                         'seq', jsonb_array_length(chats) + 1, 'branch_source', NULL, 'created_at', CAST(:now AS text)))
                WHERE id = :node_id
            """),
            {"node_id": write_node_id, "user_text": user_text, "assistant_text": assistant_text, "now": now},
        )
        if result.rowcount != 1:
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
    _: User = Depends(get_current_user),
):
    node = await db.get(Node, node_id)  # RLS: nodes of invisible projects are simply absent
    if node is None:
        raise HTTPException(404, "Node not found")
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
    for leaf_id, rows in ((a_id, path_a), (b_id, path_b)):
        for row in rows[shared:]:
            for message in _as_list(row.chats):
                chats.append({**message, "branch_source": str(leaf_id)})
    for seq, message in enumerate(chats):
        message["seq"] = seq

    sources = [a_id, b_id]
    project_id, fork = await get_write_target(db, project_id, user.id)
    if fork is not None:
        tree_id = fork.tree_map[tree_id]
        ancestor_id = fork.node_map[ancestor_id]
        sources = [fork.node_map[s] for s in sources]
        for message in chats:
            message["branch_source"] = str(fork.node_map[UUID(message["branch_source"])])

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
    messages = to_provider_messages(flatten(path), req.content)
    user_id = user.id
    await db.rollback()  # release the connection for the length of the stream; only plain values are used below

    def _error(payload: dict, fork: Optional[dict]) -> str:
        return _sse("error", {**payload, "fork": fork} if fork else payload)

    async def run(queue: "asyncio.Queue[Optional[str]]") -> None:
        """The whole write pipeline, detached from the HTTP request: fork (sharee) -> stream -> save.
        It keeps going if the client disconnects, so a closed tab neither loses the reply nor the fork."""
        fork: Optional[dict] = None
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
            try:
                async for ev in stream_openrouter(messages, req.model):
                    if "error" in ev:
                        err = ev["error"]
                        queue.put_nowait(_error({"message": err if isinstance(err, str) else json.dumps(err)}, fork))
                        return
                    if "text" in ev:
                        reply.append(ev["text"])
                        queue.put_nowait(_sse("token", {"text": ev["text"]}))
                    else:
                        done = ev
            except (httpx.HTTPError, ValueError):
                queue.put_nowait(_error({"message": "The model provider failed; nothing was saved."}, fork))
                return

            answer = "".join(reply)
            if not answer:
                queue.put_nowait(_error({"message": "The model returned an empty reply; nothing was saved."}, fork))
                return
            try:
                await _persist(user_id, write_node_id, req.content, answer)
            except Exception:
                log.exception("saving chat to node %s failed", write_node_id)
                queue.put_nowait(_error({"message": "The reply could not be saved."}, fork))
                return
            queue.put_nowait(_sse("done", {**done, "fork": fork} if fork else done))
        except Exception:
            log.exception("chat pipeline for node %s crashed", node_id)
            queue.put_nowait(_error({"message": "Something went wrong; the reply may not have been saved."}, fork))
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