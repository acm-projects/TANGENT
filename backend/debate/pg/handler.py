from __future__ import annotations

import asyncio
import importlib
import json
import os
from typing import Any, Optional

from ..openrouter import OpenRouterBrain, OpenRouterClient
from . import store
from .adapters import make_summarizer
from .checkpointer import open_saver, purge_thread
from .db import make_engine, make_factory
from .queue import Enqueuer, SqsEnqueuer
from .worker import WorkerEnv, run_debate


def load_search() -> Any:
    ref = os.environ.get("DEBATE_SEARCH_FACTORY", "debate.search_s2:from_env")
    module, _, name = ref.partition(":")
    return getattr(importlib.import_module(module), name)()


def build_env(search: Optional[Any] = None) -> tuple[WorkerEnv, OpenRouterClient]:
    url = os.environ["DATABASE_URL"]
    client = OpenRouterClient(
        os.environ["OPENROUTER_DEBATE_API_KEY"],
        app_url=os.environ.get("APP_URL", ""),
        reasoning_effort=os.environ.get("DEBATE_REASONING_EFFORT") or None,
    )
    summary_model = os.environ.get("DEBATE_SUMMARY_MODEL")
    env = WorkerEnv(
        factory=make_factory(make_engine(url)),
        database_url=url,
        make_brain=lambda row: OpenRouterBrain(
            client, for_model=row["for_model"], against_model=row["against_model"], judge_model=row["judge_model"]
        ),
        search=search or load_search(),
        summarize=make_summarizer(client, summary_model) if summary_model else None,
        token_budget=int(os.environ.get("DEBATE_CONTEXT_TOKENS", "24000")),
        max_cost_usd=float(os.environ["DEBATE_MAX_COST_USD"]) if os.environ.get("DEBATE_MAX_COST_USD") else None,
        min_slice_ms=int(os.environ.get("DEBATE_MIN_SLICE_MS", "150000")),
    )
    return env, client


async def handle(event: dict[str, Any], context: Any, env: WorkerEnv, enqueuer: Enqueuer) -> dict[str, Any]:
    """SQS batch handler. Returns partial-batch failures so only the failed messages come back."""
    failures: list[dict[str, str]] = []
    for rec in event.get("Records", []):
        try:
            msg = json.loads(rec["body"])
            attempt = int(rec.get("attributes", {}).get("ApproximateReceiveCount", 1))
            outcome = await run_debate(
                env, msg["debate_id"], time_left_ms=context.get_remaining_time_in_millis, attempt=attempt
            )
            if outcome == "continue":
                await enqueuer.enqueue(msg["debate_id"])
            elif outcome == "busy":
                failures.append({"itemIdentifier": rec["messageId"]})
        except Exception:
            failures.append({"itemIdentifier": rec["messageId"]})
    return {"batchItemFailures": failures}


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    async def go() -> dict[str, Any]:
        env, client = build_env()
        try:
            return await handle(event, context, env, SqsEnqueuer(os.environ["DEBATE_QUEUE_URL"]))
        finally:
            await client._http.aclose()

    return asyncio.run(go())


async def sweep(env: WorkerEnv, enqueuer: Enqueuer, *, events_ttl_s: int = 600) -> dict[str, Any]:
    expired = await store.expire_overdue(env.factory)
    stuck = await store.find_stuck(env.factory)
    for debate_id in stuck:
        await enqueuer.enqueue(debate_id)
    events = await store.purge_finished_events(env.factory, events_ttl_s)
    cleaned = await store.finished_without_cleanup(env.factory)
    if cleaned:
        async with open_saver(env.database_url) as saver:
            for debate_id in cleaned:
                await purge_thread(saver, debate_id)
    return {"expired": expired, "requeued": stuck, "events_purged": events, "checkpoints_checked": len(cleaned)}


def sweeper(event: dict[str, Any], context: Any) -> dict[str, Any]:
    async def go() -> dict[str, Any]:
        env, client = build_env(search=_NoSearch())
        try:
            return await sweep(env, SqsEnqueuer(os.environ["DEBATE_QUEUE_URL"]))
        finally:
            await client._http.aclose()

    return asyncio.run(go())


class _NoSearch:
    async def search(self, query: str) -> list[Any]:
        raise RuntimeError("the sweeper does not search")
