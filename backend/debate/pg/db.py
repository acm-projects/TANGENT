from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Optional
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

SYSTEM_JOB = "debate_maintenance"


LOCAL_HOSTS = (None, "", "localhost", "127.0.0.1")


def normalize_url(raw: str) -> str:
    """Accept what the backend's .env holds: `jdbc:postgresql://host:5432/db` with no credentials, plus DB_USER and
    DB_PASSWORD in the environment (see app/database.py). Returns a plain libpq-style URL. Remote hosts get
    sslmode=require unless the URL already says otherwise."""
    url = make_url(raw.removeprefix("jdbc:")).set(drivername="postgresql")
    if not url.username and os.environ.get("DB_USER"):
        url = url.set(username=os.environ["DB_USER"], password=os.environ.get("DB_PASSWORD"))
    query = dict(url.query)
    if url.host not in LOCAL_HOSTS and "sslmode" not in query and "ssl" not in query:
        query["sslmode"] = "require"
    return url.set(query=query).render_as_string(hide_password=False)


def _rewrite(url: str, scheme: str, rename: dict[str, str], extra: Optional[dict[str, str]] = None) -> str:
    parts = urlsplit(url)
    query = [(rename.get(k, k), v) for k, v in parse_qsl(parts.query, keep_blank_values=True)]
    for k, v in (extra or {}).items():
        query.append((k, v))
    return urlunsplit((scheme, parts.netloc, parts.path, urlencode(query, quote_via=quote), parts.fragment))


def asyncpg_url(url: str) -> str:
    return _rewrite(normalize_url(url), "postgresql+asyncpg", {"sslmode": "ssl"})


def psycopg_sa_url(url: str) -> str:
    return _rewrite(normalize_url(url), "postgresql+psycopg", {"ssl": "sslmode"})


def psycopg_dsn(url: str, schema: str = "langgraph") -> str:
    return _rewrite(normalize_url(url), "postgresql", {"ssl": "sslmode"}, {"options": f"-c search_path={schema}"})


def make_engine(url: str, *, driver: Optional[str] = None, null_pool: bool = True, **kw: Any) -> AsyncEngine:
    driver = driver or os.environ.get("DEBATE_DB_DRIVER", "psycopg")
    if driver not in ("psycopg", "asyncpg"):
        raise ValueError("driver must be psycopg or asyncpg")
    if null_pool:
        kw["poolclass"] = NullPool
    if driver == "asyncpg":
        kw.setdefault("connect_args", {"statement_cache_size": 0})  # same setting the backend uses
        return create_async_engine(asyncpg_url(url), **kw)
    return create_async_engine(psycopg_sa_url(url), **kw)


def make_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


@asynccontextmanager
async def tx(
    factory: async_sessionmaker[AsyncSession],
    *,
    user_id: Optional[str] = None,
    system_job: bool = False,
) -> AsyncIterator[AsyncSession]:
    async with factory() as session:
        async with session.begin():
            if user_id:
                await session.execute(text("SELECT set_config('app.current_user_id', :u, true)"), {"u": str(user_id)})
            if system_job:
                await session.execute(text("SELECT set_config('app.system_job', :j, true)"), {"j": SYSTEM_JOB})
            yield session


def js(value: Any) -> str:
    return json.dumps(value, default=str)
