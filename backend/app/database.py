import os
import uuid
from typing import AsyncGenerator

from fastapi import Request
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import event, text
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is missing!")

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    future=True,
    pool_size=20,
    max_overflow=10,
    connect_args={"statement_cache_size": 0}
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False
)


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