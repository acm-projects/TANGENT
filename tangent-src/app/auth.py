"""
Tangent — auth.py
"""

import os
from typing import Optional
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from jose import JWTError, jwt

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.database import get_db_session
from app.models import User


JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
if not JWT_SECRET_KEY:
    raise ValueError("JWT_SECRET_KEY environment variable is missing!")

ALGORITHM = "HS256"
bearer_scheme = HTTPBearer()

ACCESS_TOKEN_EXPIRE = timedelta(hours=6)
REFRESH_TOKEN_EXPIRE = timedelta(days=7)
REFRESH_GRACE_PERIOD = timedelta(seconds=120)
DELETE_CONFIRM_TOKEN_EXPIRE = timedelta(minutes=5)


def create_access_token(data: dict, expires_delta: timedelta = ACCESS_TOKEN_EXPIRE) -> str:
    to_encode = data.copy()
    to_encode["iat"] = datetime.now(timezone.utc)
    to_encode["exp"] = datetime.now(timezone.utc) + expires_delta
    to_encode["type"] = "access"
    return jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(data: dict, expires_delta: timedelta = REFRESH_TOKEN_EXPIRE) -> str:
    to_encode = data.copy()
    to_encode["iat"] = datetime.now(timezone.utc)
    to_encode["exp"] = datetime.now(timezone.utc) + expires_delta
    to_encode["type"] = "refresh"
    return jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=ALGORITHM)


def create_delete_confirmation_token(data: dict, expires_delta: timedelta = DELETE_CONFIRM_TOKEN_EXPIRE) -> str:
    """
    Issued only by /auth/callback/reauth/google once it has verified the
    user just re-authenticated with the SAME Google account as their
    existing session. Single-purpose and short-lived on purpose — it can
    only be consumed by DELETE /auth/me, and only within 5 minutes.
    """
    to_encode = data.copy()
    to_encode["iat"] = datetime.now(timezone.utc)
    to_encode["exp"] = datetime.now(timezone.utc) + expires_delta
    to_encode["type"] = "delete_confirm"
    return jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=ALGORITHM)


def verify_delete_confirmation_token(token: str, expected_user_id: str) -> bool:
    """
    Used by DELETE /auth/me. Returns True only if `token` is a valid,
    unexpired delete_confirm token minted for THIS user — not just any
    valid delete_confirm token, since that would let a token meant for
    one account be replayed against another.
    """
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return False
    return payload.get("type") == "delete_confirm" and payload.get("sub") == str(expected_user_id)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db_session),
) -> User:
    """
    Decodes the access token and loads the user. This is the only user-level
    auth dependency Tangent's routers need — there's no workspace/project
    role to attach here. Project-level access (which trees/nodes a user can
    see or write into) is enforced by RLS via `has_project_access`, using
    `app.current_user_id` set per-transaction in `get_db_session` — not by
    this function.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    token = credentials.credentials
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[ALGORITHM])
        user_id: Optional[str] = payload.get("sub")
        token_type: Optional[str] = payload.get("type")

        if not user_id or token_type != "access":
            raise credentials_exception

    except JWTError:
        raise credentials_exception

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise credentials_exception

    return user