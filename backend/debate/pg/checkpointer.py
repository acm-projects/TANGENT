from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from .db import psycopg_dsn


@asynccontextmanager
async def open_saver(database_url: str) -> AsyncIterator[AsyncPostgresSaver]:
    async with AsyncPostgresSaver.from_conn_string(psycopg_dsn(database_url)) as saver:
        yield saver


async def setup_saver(database_url: str) -> None:
    async with open_saver(database_url) as saver:
        await saver.setup()


async def purge_thread(saver: Any, debate_id: str) -> None:
    await saver.adelete_thread(debate_id)
