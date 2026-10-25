from __future__ import annotations

import asyncio
import json
import random
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Literal, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..assign import assign_models
from . import store
from .db import tx
from .queue import Enqueuer

ACTIVE = ("queued", "running", "awaiting_input", "finalizing")


@dataclass
class ModelOption:
    id: str
    label: str


@dataclass
class JudgeOption:
    model: str
    family: str


@dataclass
class WriteTarget:
    """Where a debate is written. For an owner it is the node they pointed at. For a sharee it is the same node in their
    own copy of the project (made on their first write, like chat), plus the fork payload for the client."""
    project_id: str
    node_id: str
    fork: Optional[dict[str, Any]] = None


# (user_id, project_id, node_id) -> WriteTarget. Raises HTTPException (for example if the sharee already has a copy).
ResolveTarget = Callable[[str, str, str], Awaitable[WriteTarget]]


@dataclass
class DebateSettings:
    allowed_models: list[ModelOption]
    judges: list[JudgeOption]
    max_active_per_user: int = 2
    dev: bool = False
    rng: random.Random = field(default_factory=random.SystemRandom)  # side assignment when two models are sent
    default_model: Optional[str] = None  # shown to the frontend as the preselected model
    resolve_target: Optional[ResolveTarget] = None  # forks the project for a sharee; None = owners only
    sse_poll_s: float = 1.0
    sse_stream_poll_s: float = 0.25  # poll interval while text is streaming (a `token` event in the last few seconds)
    sse_heartbeat_s: float = 15.0
    extra: dict[str, Any] = field(default_factory=dict)


def family(model_id: str) -> str:
    return model_id.split("/", 1)[0].lower()


def pick_judge(for_model: str, against_model: str, judges: list[JudgeOption]) -> str:
    used = {family(for_model), family(against_model)}
    for j in judges:
        if j.family.lower() not in used:
            return j.model
    raise ValueError("no judge model from a different family is configured")


def _is_uuid(v: str) -> bool:
    try:
        uuid.UUID(str(v))
        return True
    except ValueError:
        return False


class StartBody(BaseModel):
    project_id: str
    node_id: str
    topic: str = Field(min_length=3, max_length=2000)
    models: list[str] = Field(min_length=1, max_length=2)  # one = both sides (default); two = sides assigned at random
    rounds: int = Field(default=2, ge=1, le=3)
    retain_artifacts: bool = False

    @field_validator("project_id", "node_id")
    @classmethod
    def _ids_are_uuids(cls, v: str) -> str:
        if not _is_uuid(v):
            raise ValueError("must be a UUID")
        return v

    @field_validator("topic")
    @classmethod
    def _topic_not_blank(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 3:
            raise ValueError("topic must contain at least 3 non-space characters")
        return v


class AnswerBody(BaseModel):
    answers: dict[str, Any] = Field(default_factory=dict)
    skip: bool = False


class ControlBody(BaseModel):
    action: Literal["pick_side", "stop"]
    side: Optional[Literal["for", "against"]] = None


def sse(event: str, data: Any, event_id: Optional[int] = None) -> str:
    head = f"id: {event_id}\n" if event_id is not None else ""
    return f"{head}event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


STREAMING_PHASES = ("research", "opening", "rebuttal", "closing", "judging")  # someone is writing: poll fast

PUBLIC_FIELDS = (
    "id", "topic", "for_model", "against_model", "rounds", "status", "current_phase", "current_round",
    "pending_questions", "result_node_id", "end_reason", "error_code", "wall_ms", "active_ms", "waited_ms",
)


def public(d: dict[str, Any]) -> dict[str, Any]:
    return {k: (str(d[k]) if k in ("id", "result_node_id") and d[k] else d[k]) for k in PUBLIC_FIELDS}


def build_router(
    *,
    factory: async_sessionmaker[AsyncSession],
    current_user: Callable[..., Awaitable[str]],
    enqueue: Enqueuer,
    settings: DebateSettings,
) -> APIRouter:
    router = APIRouter(prefix="/debates", tags=["debates"])
    allowed = {m.id for m in settings.allowed_models}

    async def fetch(user: str, debate_id: str) -> dict[str, Any]:
        if not _is_uuid(debate_id):
            raise HTTPException(404, "debate not found")
        async with tx(factory, user_id=user) as s:
            d = await store.get_debate(s, debate_id)
        if d is None:
            raise HTTPException(404, "debate not found")
        return d

    async def queue(debate_id: str) -> None:
        try:
            await enqueue.enqueue(debate_id)
        except Exception:
            raise HTTPException(503, "could not queue the debate; it will be retried shortly")

    @router.get("/models")
    async def models(user: str = Depends(current_user)) -> dict[str, Any]:
        return {"models": [{"id": m.id, "label": m.label} for m in settings.allowed_models], "default": settings.default_model or settings.allowed_models[0].id, "rounds": {"default": 2, "max": 3}, "model_modes": {"same": "send one model, used for both sides (default)", "pair": "send two models, sides are assigned at random"}}

    @router.post("", status_code=202)
    async def start(body: StartBody, user: str = Depends(current_user)) -> dict[str, Any]:
        try:
            for_model, against_model, mode = assign_models(body.models, settings.rng)
        except ValueError as e:
            raise HTTPException(422, str(e))
        for m in {for_model, against_model}:
            if m not in allowed:
                raise HTTPException(422, f"model {m!r} is not available")
        try:
            judge = pick_judge(for_model, against_model, settings.judges)
        except ValueError as e:
            raise HTTPException(503, str(e))
        async with tx(factory, user_id=user) as s:
            node = (
                await s.execute(
                    text("SELECT project_id::text FROM nodes WHERE id = CAST(:n AS uuid)"), {"n": body.node_id}
                )
            ).scalar_one_or_none()
            if node is None or node != body.project_id:
                raise HTTPException(404, "node not found in this project")
            owns = (
                await s.execute(
                    text("SELECT 1 FROM projects WHERE id = CAST(:p AS uuid) AND created_by_id = CAST(:u AS uuid)"),
                    {"p": body.project_id, "u": user},
                )
            ).first()
            if not owns and settings.resolve_target is None:
                raise HTTPException(403, "debates can only be started in your own project")
            active = (
                await s.execute(
                    text("SELECT count(*) FROM debates WHERE owner_id = CAST(:u AS uuid) AND status IN ('queued','running','awaiting_input','finalizing')"),
                    {"u": user},
                )
            ).scalar_one()
            if active >= settings.max_active_per_user:
                raise HTTPException(429, "too many debates running; wait for one to finish")
        # The cap is checked before any fork, so a refused request never copies a project.
        target = WriteTarget(body.project_id, body.node_id)
        if not owns:
            # A sharee's first write copies the project to them (committed on its own); the debate runs in their copy,
            # where they are the owner, so every owner-only rule below applies to the copy unchanged.
            target = await settings.resolve_target(user, body.project_id, body.node_id)
        async with tx(factory, user_id=user) as s:
            debate_id = await store.create_debate(
                s, owner_id=user, project_id=target.project_id, parent_node_id=target.node_id, topic=body.topic.strip(),
                for_model=for_model, against_model=against_model, judge_model=judge, rounds=body.rounds,
                retain_artifacts=bool(body.retain_artifacts and settings.dev),
            )
        await queue(debate_id)
        out = {"id": debate_id, "status": "queued", "model_mode": mode, "for_model": for_model, "against_model": against_model}
        if target.fork:
            out["fork"] = target.fork
        return out

    @router.get("/node/{node_id}")
    async def by_node(node_id: str, user: str = Depends(current_user)) -> dict[str, Any]:
        """Structured verdict behind a debate node, for the card shown above its chat."""
        if not _is_uuid(node_id):
            raise HTTPException(404, "no debate result for this node")
        async with tx(factory, user_id=user) as s:
            r = await store.get_result_by_node(s, node_id)
        if r is None:
            raise HTTPException(404, "no debate result for this node")
        r = {k: (str(v) if k in ("node_id", "debate_id") else float(v) if k in ("confidence", "cost_usd") else v) for k, v in r.items()}
        return r

    @router.get("/{debate_id}")
    async def get(debate_id: str, user: str = Depends(current_user)) -> dict[str, Any]:
        return public(await fetch(user, debate_id))

    @router.post("/{debate_id}/answer", status_code=202)
    async def answer(debate_id: str, body: AnswerBody, user: str = Depends(current_user)) -> dict[str, Any]:
        await fetch(user, debate_id)
        try:
            async with tx(factory, user_id=user) as s:
                await store.submit_answer(s, debate_id, body.answers, body.skip)
        except store.StateError as e:
            raise HTTPException(409, str(e))
        await queue(debate_id)
        return {"status": "queued"}

    @router.post("/{debate_id}/control", status_code=202)
    async def control(debate_id: str, body: ControlBody, user: str = Depends(current_user)) -> dict[str, Any]:
        await fetch(user, debate_id)
        try:
            async with tx(factory, user_id=user) as s:
                r = await store.request_control(s, debate_id, body.action, body.side)
        except store.StateError as e:
            raise HTTPException(409, str(e))
        if r["needs_resume"]:
            await queue(debate_id)
        return {"control": r["control"]["id"], "resumed": r["needs_resume"]}

    @router.post("/{debate_id}/cancel", status_code=202)
    async def cancel(debate_id: str, user: str = Depends(current_user)) -> dict[str, Any]:
        await fetch(user, debate_id)
        async with tx(factory, user_id=user) as s:
            ok = await store.cancel_debate(s, debate_id)
        if not ok:
            raise HTTPException(409, "debate is not active")
        return {"status": "cancelled"}

    @router.get("/{debate_id}/events")
    async def events(
        debate_id: str,
        request: Request,
        user: str = Depends(current_user),
        after: Optional[int] = Query(default=None),
        last_event_id: Optional[str] = Header(default=None),
    ) -> StreamingResponse:
        first = await fetch(user, debate_id)
        cursor = after if after is not None else int(last_event_id) if (last_event_id or "").isdigit() else 0

        async def gen() -> Any:
            nonlocal cursor
            yield sse("state", public(first))
            idle = 0.0
            settled = False
            fast_until = 0.0
            while True:
                if await request.is_disconnected():
                    return
                async with tx(factory, user_id=user) as s:
                    evs = await store.read_events(s, debate_id, cursor)
                    d = await store.get_debate(s, debate_id)
                for e in evs:
                    cursor = e["id"]
                    if e["type"] == "token":
                        fast_until = time.monotonic() + 3.0
                    yield sse(e["type"], {"payload": e["payload"], "at": e["created_at"]}, e["id"])
                if d is None:
                    return
                if d["status"] in store.TERMINAL and not evs:
                    if settled:
                        yield sse("done", public(d))
                        return
                    settled = True  # the last event is written just after the status flips, so look once more
                    await asyncio.sleep(settings.sse_poll_s)
                    continue
                writing = d.get("status") == "running" and d.get("current_phase") in STREAMING_PHASES
                nap = settings.sse_stream_poll_s if (writing or time.monotonic() < fast_until) else settings.sse_poll_s
                if evs:
                    idle = 0.0
                else:
                    idle += nap
                    if idle >= settings.sse_heartbeat_s:
                        idle = 0.0
                        yield ": ping\n\n"
                await asyncio.sleep(nap)

        return StreamingResponse(
            gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"}
        )

    return router