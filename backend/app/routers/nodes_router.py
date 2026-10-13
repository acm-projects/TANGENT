import json
import logging
from datetime import datetime, timezone
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.context.flatten import flatten, to_provider_messages
from app.context.schemas import PathNode
from app.core.openrouter import DEFAULT_MODEL_ID, get_model_or_400, stream_openrouter
from app.database import AsyncSessionLocal, get_db_session
from app.models import User

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


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


async def _load_path(db: AsyncSession, node_id: UUID) -> list[PathNode]:
    rows = (await db.execute(_PATH_SQL, {"node_id": node_id})).all()
    if not rows:
        raise HTTPException(404, "Node not found")
    is_parent = (
        await db.execute(text("SELECT 1 FROM nodes WHERE parent_id = :id LIMIT 1"), {"id": node_id})
    ).first()
    if is_parent:
        # ARCHITECTURE.md §8: only leaves take prompts. The UI hint is not enforcement; this is.
        raise HTTPException(409, "Only a leaf node can be prompted; fork it instead")
    return [PathNode(id=r.id, chats=r.chats) for r in rows]


async def _persist(user_id: UUID, node_id: UUID, user_text: str, assistant_text: str) -> None:
    """Append the exchange to nodes.chats. Own session: the request's may already be closed once
    the stream ends. `||` appends atomically (no read-modify-write); seq is the new array index."""
    now = datetime.now(timezone.utc).isoformat()
    async with AsyncSessionLocal() as session, session.begin():
        await session.execute(
            text("SELECT set_config('app.current_user_id', :uid, true)"), {"uid": str(user_id)}
        )
        await session.execute(
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
            {"node_id": node_id, "user_text": user_text, "assistant_text": assistant_text, "now": now},
        )


@router.post("/{node_id}/messages")
async def send_message(
    node_id: UUID,
    req: MessageRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Prompt a leaf node; stream the reply as SSE `token {text}`, then `done` or `error {message}`.
    The server rebuilds the history from the tree; the client sends only the new message."""
    get_model_or_400(req.model)
    path = await _load_path(db, node_id)
    messages = to_provider_messages(flatten(path), req.content)
    user_id = user.id

    async def events():
        reply: list[str] = []
        done: dict = {}
        try:
            async for ev in stream_openrouter(messages, req.model):
                if "error" in ev:
                    err = ev["error"]
                    yield _sse("error", {"message": err if isinstance(err, str) else json.dumps(err)})
                    return
                if "text" in ev:
                    reply.append(ev["text"])
                    yield _sse("token", {"text": ev["text"]})
                else:
                    done = ev
        except (httpx.HTTPError, ValueError):
            yield _sse("error", {"message": "The model provider failed; nothing was saved."})
            return

        answer = "".join(reply)
        if not answer:
            yield _sse("error", {"message": "The model returned an empty reply; nothing was saved."})
            return
        try:
            await _persist(user_id, node_id, req.content, answer)
        except Exception:
            log.exception("saving chat to node %s failed", node_id)
            yield _sse("error", {"message": "The reply could not be saved."})
            return
        yield _sse("done", done)

    return StreamingResponse(events(), media_type="text/event-stream")
