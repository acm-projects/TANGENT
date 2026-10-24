"""Drop into app/routers/debates_router.py, then in main.py:

    from app.routers import debates_router
    app.include_router(debates_router.router)

The debate package (the `debate/` folder) must be importable from the backend (copy it next to `app/` or install it).
The router uses YOUR asyncpg session factory, so debate endpoints share the backend's pool and SSL settings.
Workers (Lambda) use psycopg through debate.pg.db.make_engine. Both read the same DATABASE_URL.
"""
import os
from uuid import UUID

from fastapi import Depends, HTTPException
from sqlalchemy import text

from app.auth import get_current_user
from app.database import AsyncSessionLocal
from app.models import User
from app.project_forking import build_fork_info, copy_exists_error, get_user_copy, get_write_target
from debate.pg.api import DebateSettings, JudgeOption, ModelOption, WriteTarget, build_router
from debate.pg.local import InlineEnqueuer
from debate.pg.queue import SqsEnqueuer


async def current_user_id(user: User = Depends(get_current_user)) -> str:
    return str(user.id)


async def resolve_target(user_id: str, project_id: str, node_id: str) -> WriteTarget:
    """Called only when the caller is NOT the project owner (a sharee). Mirrors nodes_router._prepare_write: fork the
    project for them in its own committed session, then map the node into their copy. The debate is then created in the
    copy, where the sharee is the owner. If they already have a copy, the original's node ids mean nothing there, so
    redirect exactly like chat does (copy_exists_error)."""
    uid, pid, nid = UUID(user_id), UUID(project_id), UUID(node_id)
    async with AsyncSessionLocal() as session, session.begin():
        await session.execute(text("SELECT set_config('app.current_user_id', :uid, true)"), {"uid": user_id})
        if await get_user_copy(session, pid, uid) is not None:
            raise copy_exists_error((await get_user_copy(session, pid, uid)).id)
        write_project_id, fork = await get_write_target(session, pid, uid)
        if fork is None:  # not expected for a non-owner; refuse rather than write into someone else's project
            raise HTTPException(403, "debates can only be started in your own project")
        info = await build_fork_info(session, fork)
        write_node_id = fork.node_map[nid]
        return WriteTarget(
            project_id=str(write_project_id),
            node_id=str(write_node_id),
            fork={**info.model_dump(mode="json"), "node_id": str(write_node_id)},
        )


# Debater models the client may choose (OpenRouter ids). First test: Haiku debates both sides, Luna judges.
# Verify the exact ids in app.core.openrouter.AVAILABLE_MODELS / OpenRouter before the first run.
ALLOWED = [
    ModelOption("anthropic/claude-haiku-5.5", "Claude Haiku 5.5"),
    ModelOption("openai/gpt-6-luna", "GPT-6 Luna"),
]
DEFAULT_MODEL = "anthropic/claude-haiku-5.5"
# The judge is chosen on the server: first entry whose family differs from both debaters.
# Haiku debaters -> Luna judges. Luna debaters -> Haiku judges. Argon is the fallback (e.g. if both families debate).
JUDGES = [
    JudgeOption("openai/gpt-6-luna", "openai"),
    JudgeOption("anthropic/claude-haiku-5.5", "anthropic"),
    JudgeOption("google/gemini-4-argon", "google"),
]

router = build_router(
    factory=AsyncSessionLocal,
    current_user=current_user_id,
    # Production: SQS -> Lambda. Local dev (no DEBATE_QUEUE_URL): run the same worker inside this process.
    enqueue=SqsEnqueuer(os.environ["DEBATE_QUEUE_URL"]) if os.environ.get("DEBATE_QUEUE_URL") else InlineEnqueuer(),
    settings=DebateSettings(allowed_models=ALLOWED, judges=JUDGES, default_model=DEFAULT_MODEL, resolve_target=resolve_target, dev=os.getenv("IS_PRODUCTION") != "1"),
)
