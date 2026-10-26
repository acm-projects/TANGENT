import asyncio
import logging
import os
import uuid
from typing import AsyncGenerator

from fastapi import Request
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import event, select, text
from sqlalchemy.engine import make_url
from dotenv import load_dotenv

from app.models import Base

load_dotenv()

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")

_raw_url = os.getenv("DATABASE_URL")
if not _raw_url:
    raise ValueError("DATABASE_URL environment variable is missing!")


def _build_url(raw: str):
    """The team's shared .env holds a JDBC-style URL (jdbc:postgresql://host:5432/db) with no
    credentials. Accept that or a normal SQLAlchemy URL, force the asyncpg driver, and fill in
    DB_USER / DB_PASSWORD (from the environment) when the URL carries none."""
    url = make_url(raw.removeprefix("jdbc:")).set(drivername="postgresql+asyncpg")
    if not url.username and os.getenv("DB_USER"):
        url = url.set(username=os.getenv("DB_USER"), password=os.getenv("DB_PASSWORD"))
    # asyncpg takes `ssl`, not libpq's `sslmode`; we set ssl in connect_args below.
    return url.difference_update_query(["sslmode", "ssl"])


DATABASE_URL = _build_url(_raw_url)
_local = DATABASE_URL.host in (None, "localhost", "127.0.0.1")

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    future=True,
    pool_size=20,
    max_overflow=10,
    # ponytail: remote hosts (RDS) use ssl="require": encrypted but cert not verified; load the AWS CA bundle to verify.
    connect_args={"statement_cache_size": 0, **({} if _local else {"ssl": "require"})},
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False
)


# Columns added after the first schema. The models define them but nothing migrates existing databases,
# so each startup adds any that are missing (IF NOT EXISTS: safe to repeat).
# ponytail: hand-rolled; move to Alembic once this list is more than a handful of columns.
_ADDED_COLUMNS = [
    "ALTER TABLE invitations ADD COLUMN IF NOT EXISTS branch_node_id uuid REFERENCES nodes(id) ON DELETE CASCADE",
    "ALTER TABLE shares ADD COLUMN IF NOT EXISTS branch_node_id uuid REFERENCES nodes(id) ON DELETE CASCADE",
    # Research papers (app/papers/). Raw SQL only, no ORM models, so warm_pool doesn't read them.
    """CREATE TABLE IF NOT EXISTS papers (
        id bigserial PRIMARY KEY,
        source text NOT NULL,                  -- 's2' | 'upload'
        source_id text NOT NULL,               -- S2 paperId, or '{project_id}:{sha256}' for uploads
        project_id uuid REFERENCES projects(id) ON DELETE CASCADE,  -- uploads only; S2 papers are global
        title text NOT NULL,
        authors jsonb NOT NULL DEFAULT '[]'::jsonb,
        year int,
        abstract text,
        doi text,
        arxiv_id text,
        pdf_url text,
        status text NOT NULL DEFAULT 'metadata_only',
        pdf_sha256 text,
        page_count int,
        pipeline_version int,
        error text,
        search_tsv tsvector GENERATED ALWAYS AS
            (to_tsvector('english', coalesce(title, '') || ' ' || coalesce(abstract, ''))) STORED,
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now(),
        UNIQUE (source, source_id)
    )""",
    "CREATE INDEX IF NOT EXISTS papers_search_tsv_idx ON papers USING gin (search_tsv)",
    """CREATE TABLE IF NOT EXISTS paper_files (
        sha256 text PRIMARY KEY,
        bytes bytea NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now()
    )""",
    """CREATE TABLE IF NOT EXISTS paper_chunks (
        paper_id bigint NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
        idx int NOT NULL,
        section text,
        page_start int NOT NULL,
        page_end int NOT NULL,
        text text NOT NULL,
        tsv tsvector GENERATED ALWAYS AS
            (to_tsvector('english', coalesce(section, '') || ' ' || text)) STORED,
        PRIMARY KEY (paper_id, idx)
    )""",
    "CREATE INDEX IF NOT EXISTS paper_chunks_tsv_idx ON paper_chunks USING gin (tsv)",
    """CREATE TABLE IF NOT EXISTS ingestion_jobs (
        id bigserial PRIMARY KEY,
        paper_id bigint NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
        pipeline_version int NOT NULL,
        status text NOT NULL DEFAULT 'pending',  -- pending | running | done | failed
        attempts int NOT NULL DEFAULT 0,
        error text,
        locked_at timestamptz,
        run_after timestamptz NOT NULL DEFAULT now(),
        created_at timestamptz NOT NULL DEFAULT now(),
        UNIQUE (paper_id, pipeline_version)
    )""",
    "CREATE INDEX IF NOT EXISTS ingestion_jobs_pending_idx ON ingestion_jobs (run_after) WHERE status = 'pending'",
    # Semantic Scholar papers an agent read in a project, so they show in its Sources panel next to uploads.
    """CREATE TABLE IF NOT EXISTS project_papers (
        project_id uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        paper_id bigint NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
        created_at timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (project_id, paper_id)
    )""",
]


async def ensure_columns() -> None:
    """Best effort like warm_pool: startup must not depend on the database being up or on DDL rights."""
    try:
        async with engine.begin() as conn:
            for statement in _ADDED_COLUMNS:
                await conn.execute(text(statement))
    except Exception as exc:
        logging.getLogger("uvicorn.error").warning("Schema check skipped: %s", type(exc).__name__)


async def warm_pool(n: int = 3) -> None:
    """Open n connections up front so the first requests don't each pay a fresh TLS + auth
    handshake, plus asyncpg's one-off per-connection lookup of the enum types the tables use
    (together ~1.3 s to RDS). A LIMIT 0 read of every table triggers that lookup; SELECT 1
    does not. Best effort: startup must not depend on the database being up."""
    async def _open():
        async with engine.connect() as conn:
            for table in Base.metadata.tables.values():
                await conn.execute(select(table).limit(0))

    try:
        await asyncio.gather(*(_open() for _ in range(n)))
    except Exception as exc:
        logging.getLogger("uvicorn.error").warning("Pool warm-up skipped: %s", type(exc).__name__)


def _user_id_from_request(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=["HS256"])
        if payload.get("type") != "access":
            return None
        return str(uuid.UUID(payload.get("sub")))
    except (JWTError, ValueError, TypeError):
        return None


async def get_db_session(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that yields a database session.
    The user id comes only from a verified access token in the Authorization
    header, never from request parameters. When a verified user is present,
    app.current_user_id is set at the start of every transaction on the
    session (including ones that begin after a commit), so has_project_access()
    and the RLS policies resolve the current user for the whole request.
    Requests without a valid token get a session with no identity.
    """
    user_id = _user_id_from_request(request)

    async with AsyncSessionLocal() as session:
        if user_id:
            @event.listens_for(session.sync_session, "after_begin")
            def set_current_user(sync_session, transaction, connection):
                connection.execute(
                    text("SELECT set_config('app.current_user_id', :user_id, true)"),
                    {"user_id": user_id},
                )

        yield session