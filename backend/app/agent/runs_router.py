"""HTTP API of the agent runtime: start a run, follow it (SSE, replayable), answer its questions, cancel it, and read
its full trace. The run itself is driven by worker.py, never by a request, so closing the tab changes nothing.
Owner-only: the agent's tools write to the tree."""

import asyncio
import json
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent import store
from app.auth import get_current_user
from app.core.openrouter import DEFAULT_MODEL_ID, get_model_or_400
from app.database import get_db_session
from app.models import User
from app.routers.projects_router import require_owner

router = APIRouter(prefix="/projects/{project_id}/agent/runs", tags=["Agent runs"])

TERMINAL = ("completed", "failed", "cancelled")
POLL_SECONDS = 0.7
HEARTBEAT_SECONDS = 15


class CreateRun(BaseModel):
    goal: str = Field(min_length=5, max_length=4000)
    model: str = DEFAULT_MODEL_ID
    active_node_id: Optional[UUID] = None


class Answer(BaseModel):
    answers: dict[str, str | list[str]]


def sse(event: str, data: Any, event_id: int | None = None) -> str:
    head = f"id: {event_id}\n" if event_id is not None else ""
    return f"{head}event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


async def _own(project_id: UUID, run_id: UUID, user: User) -> dict:
    run = await store.get_run(str(run_id), str(project_id), str(user.id))
    if run is None:
        raise HTTPException(404, "Run not found")
    return run


@router.post("", status_code=201)
async def create_run(project_id: UUID, req: CreateRun, db: AsyncSession = Depends(get_db_session),
                     user: User = Depends(get_current_user)):
    get_model_or_400(req.model)
    await require_owner(db, project_id, user)
    user_id = user.id  # read before rollback: it expires `user`
    await db.rollback()
    try:
        run_id = await store.create_run(project_id, user_id, req.model, req.goal.strip(), req.active_node_id)
    except store.ActiveRunExists:
        raise HTTPException(409, "This project already has a live agent run; wait for it or cancel it") from None
    return await store.get_run(run_id, str(project_id), str(user_id))


@router.get("/{run_id}")
async def get_run(project_id: UUID, run_id: UUID, user: User = Depends(get_current_user)):
    return await _own(project_id, run_id, user)


@router.get("/{run_id}/events")
async def events(project_id: UUID, run_id: UUID, request: Request, user: User = Depends(get_current_user),
                 after: Optional[int] = Query(default=None), last_event_id: Optional[str] = Header(default=None)):
    """The run's event log from `after` / Last-Event-ID (default: the start), then live. Replaying from 0 rebuilds the
    whole run, so a client that lost its connection or its state needs nothing else."""
    await _own(project_id, run_id, user)
    cursor = after if after is not None else int(last_event_id) if (last_event_id or "").isdigit() else 0
    rid = str(run_id)

    async def gen():
        nonlocal cursor
        idle = 0.0
        while True:
            if await request.is_disconnected():
                return
            evs, status = await store.read_events(rid, cursor)
            for e in evs:
                cursor = e["id"]
                yield sse(e["type"], {"payload": e["payload"], "at": e["created_at"]}, e["id"])
            if evs:
                idle = 0.0
                continue
            if status in TERMINAL:
                yield sse("done", {"status": status})
                return
            idle += POLL_SECONDS
            if idle >= HEARTBEAT_SECONDS:
                idle = 0.0
                yield ": ping\n\n"
            await asyncio.sleep(POLL_SECONDS)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"})


@router.post("/{run_id}/answer")
async def answer(project_id: UUID, run_id: UUID, req: Answer, user: User = Depends(get_current_user)):
    await _own(project_id, run_id, user)
    try:
        await store.submit_answer(str(run_id), req.answers)
    except store.AnswerError as exc:
        raise HTTPException(422, str(exc)) from None
    return await _own(project_id, run_id, user)


@router.post("/{run_id}/cancel")
async def cancel(project_id: UUID, run_id: UUID, user: User = Depends(get_current_user)):
    await _own(project_id, run_id, user)
    await store.cancel_run(str(run_id))
    return await _own(project_id, run_id, user)


@router.get("/{run_id}/trace")
async def trace(project_id: UUID, run_id: UUID, user: User = Depends(get_current_user)):
    """For developers: every model request and response, tool call, result, retry and event of the run."""
    await _own(project_id, run_id, user)
    return await store.trace(str(run_id))
