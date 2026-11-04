"""Background runner for agent runs: claim a queued (or abandoned) run, drive its loop, repeat.

Runs as tasks inside the API process (main.lifespan), like the paper worker. Claims use FOR UPDATE SKIP LOCKED and a
lock timestamp refreshed while a run is driven, so several workers or processes never take one run twice and a run whose
process died is picked up again after STALE_SECONDS. All state lives in the database: a restart loses nothing."""

import asyncio
import contextlib
import logging

from app.agent import loop, store

log = logging.getLogger(__name__)

WORKERS = 3  # runs driven at once; each is sequential inside
HEARTBEAT_SECONDS = 30
POLL_SECONDS = 1.0  # a created or answered run starts within this long


async def _beat(run_id: str) -> None:
    while True:
        await asyncio.sleep(HEARTBEAT_SECONDS)
        with contextlib.suppress(Exception):
            await store.heartbeat(run_id)


async def run_once() -> bool:
    run_id = await store.claim()
    if run_id is None:
        return False
    beat = asyncio.create_task(_beat(run_id))
    try:
        await loop.run_loop(run_id)
    except Exception as exc:
        log.exception("agent run %s failed", run_id)
        await store.fail_run(run_id, f"{type(exc).__name__}: {exc}")
    finally:
        beat.cancel()
    return True


async def run_forever() -> None:
    delay = POLL_SECONDS
    while True:
        try:
            if await run_once():
                delay = POLL_SECONDS
                continue
            delay = POLL_SECONDS
        except Exception as exc:  # database down, tables missing: back off, never crash the app
            log.warning("agent worker: %s; retrying in %.0fs", type(exc).__name__, delay)
            delay = min(delay * 2, 60)
        await asyncio.sleep(delay)
