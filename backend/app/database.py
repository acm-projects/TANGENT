import os
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import text
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

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


async def get_db_session(user_id: str = None) -> AsyncSession:
    """
    FastAPI dependency that yields a database session.
    CRITICAL: If a user_id is provided, it injects it into the Postgres
    transaction context so has_project_access() in every RLS policy can
    resolve the current user and enforce project-membership/share-based
    row isolation.
    """
    async with AsyncSessionLocal() as session:
        try:
            if user_id:
                await session.execute(
                    text("SET LOCAL app.current_user_id = :user_id"),
                    {"user_id": user_id}
                )
            yield session
        finally:
            await session.close()