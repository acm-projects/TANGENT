"""Gent's conversations, kept in the database: one thread per user per project (gent_threads: its Field Notes) and
the events of every run in order (gent_events). The client rebuilds the chat by replaying them through the same
reducer it uses live, so a reload, another device or a fork shows exactly what happened.

A run's `Recorder` sits between Gent and his listeners:
- it stores what the chat is built from (not the node tokens or tree refreshes, which only drive the board), with
  streamed fragments (his note, his reasoning) joined into one row;
- it keeps this run's events in memory too, so someone who opens the page mid-run gets everything so far (even
  rows the writer hasn't reached yet) and then follows live;
- it fans every event out to each listener: the stream that started the task, and any that reattached.
Writes go through one background writer per run, so Gent never waits on the database."""

import asyncio
import json
import logging
import uuid
from typing import Optional
from uuid import UUID

from sqlalchemy import text

from app import database
from app.agent import tools

log = logging.getLogger(__name__)

# what the chat is rebuilt from (gentStore.reduce); the rest only moves the board
STORED = {"task", "said", "note", "reasoning", "tool", "result", "step", "answer", "nudge", "reply", "cwd",
          "notes", "done", "error", "question_answered"}
FRAGMENTS = {"note", "reasoning"}  # streamed a few words at a time; stored joined


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


class Recorder:
    def __init__(self, run: "tools.Run"):
        self.run = run
        self.run_id = uuid.uuid4()
        self.log: list[dict] = []  # this run's stored events, fragments joined: {"type": ..., **data}
        self.listeners: set[asyncio.Queue] = set()
        self.rows: asyncio.Queue = asyncio.Queue()
        self.writer = asyncio.create_task(self._write())

    def listen(self) -> tuple[list[dict], asyncio.Queue]:
        """Everything so far, and a queue of what comes next (in one step: nothing falls between them)."""
        queue: asyncio.Queue = asyncio.Queue()
        self.listeners.add(queue)
        return [dict(e) for e in self.log], queue

    def emit(self, event: str, data: dict) -> None:
        if event != "task" and event != "said":  # the user's own words: the client that sent them shows them already
            frame = sse(event, data)
            for queue in self.listeners:
                queue.put_nowait(frame)
        if event in STORED:
            self._keep(event, data)

    def _keep(self, event: str, data: dict) -> None:
        last = self.log[-1] if self.log else None
        if (event in FRAGMENTS and last is not None and last["type"] == event and last.get("turn") == data.get("turn")
                and last.get("depth") == data.get("depth")):
            last["text"] = last.get("text", "") + data.get("text", "")
            return
        if last is not None and last["type"] in FRAGMENTS:
            self.rows.put_nowait(dict(last))  # the fragment is complete now
        entry = {"type": event, **data}
        self.log.append(entry)
        if event not in FRAGMENTS:
            self.rows.put_nowait(dict(entry))

    def close(self) -> None:
        """The run ended: flush what's left, end every listener's stream."""
        if self.log and self.log[-1]["type"] in FRAGMENTS:
            self.rows.put_nowait(dict(self.log[-1]))
        self.rows.put_nowait(None)
        for queue in self.listeners:
            queue.put_nowait(None)

    async def _write(self) -> None:
        while True:
            batch = [await self.rows.get()]
            while not self.rows.empty():
                batch.append(self.rows.get_nowait())
            done = batch[-1] is None
            rows = [r for r in batch if r is not None]
            if rows:
                try:
                    # the run's project at write time: after a fork, the rest of the run lands in the user's copy
                    await append(self.run.project_id, self.run.user_id, self.run_id, rows, self.run.notes)
                except Exception:
                    log.exception("could not store Gent's events for project %s", self.run.project_id)
            if done:
                return


async def append(project_id: UUID, user_id: UUID, run_id: UUID, rows: list[dict], notes: Optional[list]) -> None:
    async with database.AsyncSessionLocal() as db, db.begin():
        await tools._as_user(db, user_id)
        await _upsert(db, project_id, user_id, notes)
        await db.execute(
            text("INSERT INTO gent_events (project_id, user_id, run_id, event, payload) "
                 "SELECT :p, :u, :r, e->>'type', e - 'type' FROM jsonb_array_elements(CAST(:rows AS jsonb)) e"),
            {"p": project_id, "u": user_id, "r": run_id, "rows": json.dumps(rows, default=str)},
        )


async def _upsert(db, project_id: UUID, user_id: UUID, notes: Optional[list]) -> None:
    await db.execute(
        text("INSERT INTO gent_threads (project_id, user_id, notes) VALUES (:p, :u, CAST(:n AS jsonb)) "
             "ON CONFLICT (project_id, user_id) DO UPDATE SET notes = COALESCE(CAST(:n2 AS jsonb), gent_threads.notes), "
             "updated_at = now()"),
        {"p": project_id, "u": user_id, "n": json.dumps(notes or []), "n2": None if notes is None else json.dumps(notes)},
    )


async def save_notes(project_id: UUID, user_id: UUID, notes: list) -> None:
    async with database.AsyncSessionLocal() as db, db.begin():
        await tools._as_user(db, user_id)
        await _upsert(db, project_id, user_id, notes)


async def load(project_id: UUID, user_id: UUID, skip_run: Optional[UUID] = None) -> tuple[list[dict], list]:
    """The thread's events in order (leaving out a run still in memory) and its Field Notes."""
    async with tools._session(user_id) as db:
        notes = (await db.execute(
            text("SELECT notes FROM gent_threads WHERE project_id = :p AND user_id = :u"), {"p": project_id, "u": user_id},
        )).scalar_one_or_none()
        rows = (await db.execute(
            text("SELECT event, payload FROM gent_events WHERE project_id = :p AND user_id = :u "
                 "AND (CAST(:r AS uuid) IS NULL OR run_id <> CAST(:r AS uuid)) ORDER BY id"),
            {"p": project_id, "u": user_id, "r": skip_run},
        )).all()
    return [{"type": event, **payload} for event, payload in rows], notes or []


INTERRUPTED = ("Interrupted: the server restarted while Gent was working, so this task stopped here. Tell him to "
               "continue and he picks up from his Field Notes.")


async def close_interrupted(project_id: UUID, user_id: UUID) -> None:
    """With no run in memory, a stored run that never ended died with the server (a restart, a deploy): end it with an
    error event, so the thread doesn't show Gent as still at work.
    shortcut: runs live in one process's memory; with several workers, upgrade to a heartbeat column before relying on it."""
    async with database.AsyncSessionLocal() as db, db.begin():
        await tools._as_user(db, user_id)
        last = (await db.execute(
            # a run that just ended may still be writing its last events: only one quiet for a while counts
            text("SELECT run_id FROM gent_events WHERE project_id = :p AND user_id = :u "
                 "AND created_at < now() - interval '30 seconds' ORDER BY id DESC LIMIT 1"),
            {"p": project_id, "u": user_id})).scalar_one_or_none()
        if last is None:
            return
        ended = (await db.execute(
            text("SELECT EXISTS (SELECT 1 FROM gent_events WHERE run_id = :r AND event IN ('done', 'error'))"),
            {"r": last})).scalar_one()
        if not ended:
            await db.execute(
                text("INSERT INTO gent_events (project_id, user_id, run_id, event, payload) "
                     "VALUES (:p, :u, :r, 'error', CAST(:m AS jsonb))"),
                {"p": project_id, "u": user_id, "r": last, "m": json.dumps({"message": INTERRUPTED})})


async def clear(project_id: UUID, user_id: UUID) -> None:
    async with database.AsyncSessionLocal() as db, db.begin():
        await tools._as_user(db, user_id)
        await db.execute(text("DELETE FROM gent_threads WHERE project_id = :p AND user_id = :u"), {"p": project_id, "u": user_id})
