"""Run debates inside the backend process, with no SQS and no Lambda. For local development only.

Same worker code as the Lambda (`run_debate`), started as a background task when the API "enqueues" a debate. It
lets you try start -> SSE -> answer -> result node from the real frontend against your dev database before any AWS
exists. It has no sweeper: if the backend restarts mid-debate, that debate stays queued/running until you cancel it.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from .worker import WorkerEnv, run_debate

log = logging.getLogger(__name__)


class InlineEnqueuer:
    def __init__(self, env: Optional[WorkerEnv] = None, *, busy_retry_s: float = 2.0, max_runs: int = 200) -> None:
        self._env = env
        self.busy_retry_s, self.max_runs = busy_retry_s, max_runs
        self.tasks: set[asyncio.Task] = set()

    def _worker_env(self) -> WorkerEnv:
        if self._env is None:
            from .handler import build_env

            self._env, _client = build_env()
        return self._env

    async def enqueue(self, debate_id: str) -> None:
        task = asyncio.create_task(self._run(debate_id))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def _run(self, debate_id: str) -> None:
        try:
            env = self._worker_env()
            for _ in range(self.max_runs):
                outcome = await run_debate(env, debate_id)
                if outcome == "busy":
                    await asyncio.sleep(self.busy_retry_s)
                elif outcome != "continue":
                    return
        except Exception:
            log.exception("inline debate run failed for %s", debate_id)

    async def drain(self) -> None:
        while self.tasks:
            await asyncio.gather(*list(self.tasks), return_exceptions=True)
