from __future__ import annotations

import asyncio
import contextlib
import os
import random
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..deps import Brain, Deps, Search
from ..graph import build_graph
from ..metrics import summarize_usage
from ..openrouter import BrainError
from ..runner import build_resume, merge_pending, pending_interrupts, run_segment
from . import store
from .adapters import PgControl, PgEmitter, PgWriter, make_context_loader
from .checkpointer import open_saver, purge_thread
from .db import tx

Factory = async_sessionmaker[AsyncSession]


@dataclass
class WorkerEnv:
    factory: Factory
    database_url: str
    make_brain: Callable[[dict[str, Any]], Brain]
    search: Search
    summarize: Optional[Callable[[list[str]], Awaitable[str]]] = None
    token_budget: int = 24_000
    max_cost_usd: Optional[float] = None
    lease_ttl_s: int = 90
    heartbeat_s: float = 20.0
    min_slice_ms: int = 20_000
    max_attempts: int = 3
    # DEBATE_STREAM_TOKENS=0 turns live text off (the debate then runs on plain, non-streamed model calls).
    stream_tokens: bool = field(default_factory=lambda: os.environ.get("DEBATE_STREAM_TOKENS", "1").strip().lower() not in ("0", "false", "no", "off"))

    def __post_init__(self) -> None:
        # Same query twice (other side, later round, another debate in this process) is answered from memory.
        # DEBATE_SEARCH_CACHE=0 turns it off.
        if self.search is not None and os.environ.get("DEBATE_SEARCH_CACHE", "1").strip().lower() not in ("0", "false", "no", "off"):
            from ..search_s2 import CachedSearch
            if not isinstance(self.search, CachedSearch):
                self.search = CachedSearch(self.search)


async def _purge(env: WorkerEnv, debate_id: str, retain: bool, saver: Any) -> None:
    # Checkpoints go at once. Events stay for a few minutes so a client that reconnects can still replay,
    # and the sweeper deletes them (store.purge_finished_events).
    if retain:
        return
    await purge_thread(saver, debate_id)


async def _heartbeat(env: WorkerEnv, debate_id: str, lost: asyncio.Event) -> None:
    while True:
        await asyncio.sleep(env.heartbeat_s)
        if not await store.heartbeat(env.factory, debate_id, env.lease_ttl_s):
            lost.set()
            return


async def run_debate(
    env: WorkerEnv,
    debate_id: str,
    resume: Optional[dict[str, Any]] = None,
    *,
    time_left_ms: Callable[[], int] = lambda: 10**9,
    attempt: int = 1,
) -> str:
    row = await store.load_for_run(env.factory, debate_id)
    if row is None:
        return "noop"
    resume = resume or row.get("resume_payload")
    owner = str(row["owner_id"])
    async with open_saver(env.database_url) as saver:
        if row["status"] in store.TERMINAL:
            await _purge(env, debate_id, row["retain_artifacts"], saver)
            return "noop"
        if not await store.acquire_lease(env.factory, debate_id, env.lease_ttl_s):
            return "busy"

        writer = PgWriter(env.factory, owner)
        deps = Deps(
            brain=env.make_brain(row),
            search=env.search,
            control=PgControl(env.factory, owner),
            emitter=PgEmitter(env.factory, owner, debate_id),
            context_loader=make_context_loader(env.factory, owner, token_budget=env.token_budget, summarize=env.summarize),
            writer=writer,
            rng=random.Random(),
            max_cost_usd=env.max_cost_usd,
            stream_tokens=env.stream_tokens,
        )
        cfg = {"configurable": {"thread_id": debate_id, "deps": deps}, "recursion_limit": 200}
        graph = build_graph(saver)
        started = int(time.time() * 1000)
        writer.segment_started_ms = started

        hb: Optional[asyncio.Task] = None
        try:
            snap = await graph.aget_state(cfg)
            interrupts = pending_interrupts(snap)
            if not snap.values:
                graph_input: Any = {"debate_id": debate_id, "topic": row["topic"], "rounds": row["rounds"]}
            elif interrupts:
                if resume is None:
                    pend = merge_pending(interrupts)
                    await store.end_segment(
                        env.factory, debate_id, status="awaiting_input", pending_questions=pend, add_active=False,
                        segment={"started_at_ms": started, "ended_at_ms": started, "duration_ms": 0, "status": "paused"},
                    )
                    return "paused"
                graph_input = build_resume(interrupts, resume.get("answers"), bool(resume.get("skip")))
            else:
                graph_input = None

            lost = asyncio.Event()
            hb = asyncio.create_task(_heartbeat(env, debate_id, lost))
            run = asyncio.create_task(
                run_segment(graph, cfg, graph_input, time_left_ms=time_left_ms, min_slice_ms=env.min_slice_ms)
            )
            watcher = asyncio.create_task(lost.wait())
            done, _ = await asyncio.wait({run, watcher}, return_when=asyncio.FIRST_COMPLETED)
            if run not in done:
                run.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await run
                return "stopped"
            watcher.cancel()
            seg = run.result()

            ended = int(time.time() * 1000)
            snap = await graph.aget_state(cfg)
            values = snap.values or {}
            segment = {"started_at_ms": started, "ended_at_ms": ended, "duration_ms": ended - started, "status": seg.status}
            usage_summary = summarize_usage(values.get("usage", []))
            timings = values.get("metrics", [])

            if seg.status == "done":
                await store.end_segment(
                    env.factory, debate_id, segment=segment, status=None, add_active=False
                )
                await _purge(env, debate_id, row["retain_artifacts"], saver)
                return "done"
            if seg.status == "paused":
                pend = merge_pending(seg.interrupts)
                await store.end_segment(
                    env.factory, debate_id, segment=segment, status="awaiting_input", pending_questions=pend,
                    usage_summary=usage_summary, timings=timings,
                )
                await deps.emitter.emit(
                    "question_requested", {"questions": pend}, key=f"q:{debate_id}:{','.join(sorted(q['id'] for q in pend))}"
                )
                return "paused"
            await store.end_segment(
                env.factory, debate_id, segment=segment, status="queued", usage_summary=usage_summary, timings=timings
            )
            return "continue"
        except BrainError as e:
            await store.mark_failed(env.factory, debate_id, e.code)
            await _purge(env, debate_id, row["retain_artifacts"], saver)
            return "failed"
        except Exception:
            if attempt >= env.max_attempts:
                await store.mark_failed(env.factory, debate_id, "internal_error")
                await _purge(env, debate_id, row["retain_artifacts"], saver)
                return "failed"
            async with tx(env.factory, system_job=True) as s:
                await s.execute(
                    text("UPDATE debates SET status = 'queued', lease_until = NULL WHERE id = CAST(:d AS uuid) AND status = 'running'"),
                    {"d": debate_id},
                )
            raise
        finally:
            if hb:
                hb.cancel()