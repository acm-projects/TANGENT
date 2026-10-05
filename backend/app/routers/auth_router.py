"""
Tangent — auth_router.py
"""

import hashlib
import os
import re
import secrets
import uuid
from datetime import datetime, timezone
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, status, Response, Cookie, Request, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from jose import JWTError, jwt

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.database import get_db_session
from app.models import User, Workspace, SessionModel as Session
from app.auth import (
    create_access_token,
    create_refresh_token,
    create_delete_confirmation_token,
    verify_delete_confirmation_token,
    get_current_user,
    REFRESH_TOKEN_EXPIRE,
    REFRESH_GRACE_PERIOD,
    DELETE_CONFIRM_TOKEN_EXPIRE,
)

from app.core.oauth_utils import (
    generate_state_token,
    generate_pkce_pair,
    get_google_auth_url,
    GOOGLE_REAUTH_REDIRECT_URI,
    exchange_google_code_for_tokens,
    verify_google_id_token,
)
from app.core.utils import generate_slug

is_production = os.getenv("IS_PRODUCTION") == "1"
FRONTEND_URL = (
    os.getenv("FRONTEND_URL")
    if is_production
    else "http://localhost:5173"
)

router = APIRouter(prefix="/auth", tags=["Authentication"])

REFRESH_COOKIE_MAX_AGE = int(REFRESH_TOKEN_EXPIRE.total_seconds())


class OnboardingRequest(BaseModel):
    workspace_name: str
    next: str | None = None


class UpdateAccountRequest(BaseModel):
    name: str | None = None
    avatar_url: str | None = None

INVITE_PATH_RE = re.compile(r"/invite/[A-Za-z0-9_-]{16,128}")


def _safe_invite_path(path: str | None) -> str | None:
    """
    Only same-site invite paths may be used as a post-login destination.
    """
    if path and INVITE_PATH_RE.fullmatch(path):
        return path
    return None


def _hash_refresh_token(refresh_token: str) -> str:
    return hashlib.sha256(refresh_token.encode()).hexdigest()


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=is_production,
        samesite="none" if is_production else "lax",
        max_age=REFRESH_COOKIE_MAX_AGE,
    )



async def _get_owned_workspace_slug(db: AsyncSession, user_id) -> str | None:
    result = await db.execute(
        select(Workspace.slug)
        .where(Workspace.owner_id == user_id)
        .order_by(
            Workspace.last_used_at.desc().nulls_last(),
            Workspace.created_at.desc(),
        )
    )
    return result.scalars().first()


async def _issue_session(db: AsyncSession, user: User) -> tuple[str, str]:
    """
    Used by the Google callback: mints an access token and opens a new
    refresh Session row. Returns (access_token, refresh_token) rather than
    setting the cookie itself.
    """
    access_token = create_access_token(
        data={"sub": str(user.id), "email": user.email, "name": user.name, "jti": str(uuid.uuid4())}
    )

    session_id = str(uuid.uuid4())
    refresh_token = create_refresh_token(data={"sub": str(user.id), "jti": session_id})

    new_session = Session(
        id=session_id,
        user_id=user.id,
        refresh_token_hash=_hash_refresh_token(refresh_token),
        expires_at=datetime.now(timezone.utc) + REFRESH_TOKEN_EXPIRE,
        consumed_at=None,
    )
    db.add(new_session)
    await db.commit()

    return access_token, refresh_token


# ==========================================
# REFRESH / LOGOUT
# ==========================================

@router.post("/refresh", status_code=status.HTTP_200_OK)
async def refresh(response: Response, refresh_token: str | None = Cookie(None), db: AsyncSession = Depends(get_db_session)):
    """
    Takes a valid refresh token and returns a fresh access token (lifetime:
    ACCESS_TOKEN_EXPIRE, currently 6h). 
    """
    if not refresh_token:
        raise HTTPException(status_code=401, detail="Missing refresh token")

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
    )

    try:
        payload = jwt.decode(refresh_token, os.getenv("JWT_SECRET_KEY"), algorithms=["HS256"])
        user_id: str | None = payload.get("sub")
        token_type: str | None = payload.get("type")

        if not user_id or token_type != "refresh":
            raise credentials_exception

    except JWTError:
        raise credentials_exception

    session_result = await db.execute(
        select(Session).where(
            Session.refresh_token_hash == _hash_refresh_token(refresh_token),
            Session.user_id == user_id,
        )
    )
    active_session = session_result.scalar_one_or_none()

    if not active_session:
        raise credentials_exception

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise credentials_exception

    token_payload = {
        "sub": str(user.id),
        "email": user.email,
        "name": user.name,
        "jti": str(uuid.uuid4()),
    }

    now = datetime.now(timezone.utc)

    if active_session.consumed_at is not None:
        consumed_time = active_session.consumed_at
        if consumed_time.tzinfo is None:
            consumed_time = consumed_time.replace(tzinfo=timezone.utc)

        time_since_consumed = now - consumed_time

        if time_since_consumed <= REFRESH_GRACE_PERIOD:
            new_access_token = create_access_token(data=token_payload)
            return {"access_token": new_access_token, "token_type": "bearer"}
        else:
            await db.execute(delete(Session).where(Session.user_id == user_id))
            await db.commit()
            response.delete_cookie("refresh_token")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Security alert: Compromised token detected. All sessions terminated.",
            )
            
    active_session.consumed_at = now

    new_access_token = create_access_token(data=token_payload)

    new_session_id = str(uuid.uuid4())
    new_refresh_token = create_refresh_token(data={"sub": str(user.id), "jti": new_session_id})

    new_session = Session(
        id=new_session_id,
        user_id=user.id,
        refresh_token_hash=_hash_refresh_token(new_refresh_token),
        expires_at=now + REFRESH_TOKEN_EXPIRE,
        consumed_at=None,
    )

    _set_refresh_cookie(response, new_refresh_token)

    db.add(new_session)
    await db.commit()

    return {"access_token": new_access_token, "token_type": "bearer"}


@router.post("/logout", status_code=status.HTTP_200_OK)
async def logout(response: Response, refresh_token: str | None = Cookie(None), db: AsyncSession = Depends(get_db_session)):
    if refresh_token:
        result = await db.execute(
            select(Session).where(Session.refresh_token_hash == _hash_refresh_token(refresh_token))
        )
        active_session = result.scalar_one_or_none()

        if active_session:
            await db.delete(active_session)
            await db.commit()

    response.delete_cookie(key="refresh_token", httponly=True, secure=is_production, samesite="lax")

    return {"message": "Successfully logged out."}


@router.post("/onboarding", status_code=status.HTTP_201_CREATED)
async def onboarding(
    request: OnboardingRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """
    Creates the user's workspace when created new account.
    """
    if current_user.onboarding_completed:
        raise HTTPException(status_code=400, detail="Onboarding already completed.")

    base_slug = generate_slug(request.workspace_name)
    workspace_slug = base_slug

    while True:
        existing = (await db.execute(select(Workspace).where(Workspace.slug == workspace_slug))).scalar_one_or_none()
        if not existing:
            break
        workspace_slug = f"{base_slug}-{secrets.token_hex(2)}"

    new_workspace = Workspace(
        name=request.workspace_name,
        slug=workspace_slug,
        owner_id=current_user.id,
        last_used_at=datetime.now(timezone.utc),
    )
    db.add(new_workspace)

    current_user.onboarding_completed = True
    db.add(current_user)
    await db.commit()

    next_path = _safe_invite_path(request.next)

    return {
        "message": "Workspace created successfully.",
        "redirect": next_path or f"/{workspace_slug}",
    }


# ==========================================
# ACCOUNT MANAGEMENT
# ==========================================

@router.get("/me", status_code=status.HTTP_200_OK)
async def get_account(current_user: User = Depends(get_current_user)):
    return {
        "id": str(current_user.id),
        "email": current_user.email,
        "name": current_user.name,
        "auth_provider": current_user.auth_provider,
        "avatar_url": current_user.avatar_url,
        "onboarding_completed": current_user.onboarding_completed,
    }


@router.patch("/me", status_code=status.HTTP_200_OK)
async def update_account(
    request: UpdateAccountRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    if request.name is not None:
        current_user.name = request.name
    if request.avatar_url is not None:
        current_user.avatar_url = request.avatar_url

    db.add(current_user)
    await db.commit()

    return {"message": "Account updated successfully."}


@router.delete("/me", status_code=status.HTTP_200_OK)
async def delete_account(
    response: Response,
    delete_confirm_token: str | None = Cookie(None),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """
    Deletes the user's own account. Requires a `delete_confirm_token`
    cookie — a short-lived (5 min), single-purpose token that only
    `/auth/callback/reauth/google` can mint, and only after the user has
    just re-authenticated with the SAME Google account as their existing
    session.
    """
    if not delete_confirm_token or not verify_delete_confirmation_token(delete_confirm_token, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Please re-authenticate with Google before deleting your account.",
        )

    await db.execute(delete(Session).where(Session.user_id == current_user.id))
    await db.delete(current_user)
    await db.commit()

    response.delete_cookie(key="refresh_token", httponly=True, secure=is_production, samesite="lax")
    response.delete_cookie(key="delete_confirm_token", httponly=True, secure=is_production, samesite="lax")

    return {"message": "Account deleted."}


# ==========================================
# GOOGLE OAUTH (the only auth provider)
# ==========================================

@router.get("/login/google", status_code=status.HTTP_302_FOUND)
async def google_login(next_path: str | None = Query(None, alias="next")):
    """Departure Gate: Redirects user to Google Consent Screen"""
    state = generate_state_token()
    code_verifier, code_challenge = generate_pkce_pair()

    auth_url = get_google_auth_url(state, code_challenge)
    redirect_response = RedirectResponse(url=auth_url)

    cookie_kwargs = {
        "httponly": True,
        "secure": is_production,
        "samesite": "none" if is_production else "lax",
        "max_age": 600,
    }
    redirect_response.set_cookie("oauth_state", state, **cookie_kwargs)
    redirect_response.set_cookie("pkce_verifier", code_verifier, **cookie_kwargs)

    safe_next = _safe_invite_path(next_path)
    if safe_next:
        redirect_response.set_cookie("post_login_next", safe_next, **cookie_kwargs)

    return redirect_response


@router.get("/callback/google", status_code=status.HTTP_200_OK)
async def google_callback(request: Request, db: AsyncSession = Depends(get_db_session)):
    saved_state = request.cookies.get("oauth_state")
    code_verifier = request.cookies.get("pkce_verifier")
    returned_state = request.query_params.get("state")
    code = request.query_params.get("code")

    if not saved_state or saved_state != returned_state:
        raise HTTPException(status_code=400, detail="Invalid state parameter. Possible CSRF.")
    if not code_verifier:
        raise HTTPException(status_code=400, detail="Missing PKCE verifier. Session timed out.")

    tokens = await exchange_google_code_for_tokens(code, code_verifier)
    id_token = tokens.get("id_token")
    user_info = await verify_google_id_token(id_token)
    email = user_info.get("email")
    provider_id = str(user_info.get("sub"))

    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if not user:
        user = User(
            email=email,
            name=user_info.get("name", "Google User"),
            auth_provider="google",
            provider_id=provider_id,
            avatar_url=user_info.get("picture"),
            onboarding_completed=False,
        )
        db.add(user)
        await db.flush()

    access_token, refresh_token = await _issue_session(db, user)

    next_path = _safe_invite_path(request.cookies.get("post_login_next"))
    query = f"access_token={access_token}"

    if user.onboarding_completed:
        workspace_slug = await _get_owned_workspace_slug(db, user.id)
        if not workspace_slug:
            raise HTTPException(status_code=403, detail="User does not belong to any workspace.")
        redirect_url = f"{FRONTEND_URL}{next_path}" if next_path else f"{FRONTEND_URL}/{workspace_slug}"
    else:
        redirect_url = f"{FRONTEND_URL}/onboarding"
        if next_path:
            query += f"&next={quote(next_path, safe='')}"

    redirect_response = RedirectResponse(url=f"{redirect_url}?{query}")
    _set_refresh_cookie(redirect_response, refresh_token)
    redirect_response.delete_cookie("oauth_state")
    redirect_response.delete_cookie("pkce_verifier")
    redirect_response.delete_cookie("post_login_next")

    return redirect_response


# ==========================================
# GOOGLE RE-AUTHENTICATION (before destructive actions, e.g. delete account)
# ==========================================

@router.get("/reauth/google", status_code=status.HTTP_302_FOUND)
async def google_reauth(current_user: User = Depends(get_current_user)):
    """
    Departure Gate for re-authentication.
    """
    state = generate_state_token()
    code_verifier, code_challenge = generate_pkce_pair()

    auth_url = get_google_auth_url(state, code_challenge, GOOGLE_REAUTH_REDIRECT_URI)
    redirect_response = RedirectResponse(url=auth_url)

    cookie_kwargs = {
        "httponly": True,
        "secure": is_production,
        "samesite": "none" if is_production else "lax",
        "max_age": 600,
    }
    redirect_response.set_cookie("oauth_state", state, **cookie_kwargs)
    redirect_response.set_cookie("pkce_verifier", code_verifier, **cookie_kwargs)
    redirect_response.set_cookie("reauth_user_id", str(current_user.id), **cookie_kwargs)

    return redirect_response


@router.get("/callback/reauth/google", status_code=status.HTTP_200_OK)
async def google_reauth_callback(request: Request, db: AsyncSession = Depends(get_db_session)):
    """
    Arrival Gate for re-authentication. Verifies the Google token exactly
    like the normal callback, but instead of creating a session, checks
    that the returned identity IS `reauth_user_id` (the user who started
    this from an already-authenticated request) before minting a
    delete_confirm token.
    """
    saved_state = request.cookies.get("oauth_state")
    code_verifier = request.cookies.get("pkce_verifier")
    reauth_user_id = request.cookies.get("reauth_user_id")
    returned_state = request.query_params.get("state")
    code = request.query_params.get("code")

    if not saved_state or saved_state != returned_state:
        raise HTTPException(status_code=400, detail="Invalid state parameter. Possible CSRF.")
    if not code_verifier or not reauth_user_id:
        raise HTTPException(status_code=400, detail="Missing verifier or user context. Session timed out.")

    tokens = await exchange_google_code_for_tokens(code, code_verifier, GOOGLE_REAUTH_REDIRECT_URI)
    id_token = tokens.get("id_token")
    user_info = await verify_google_id_token(id_token)
    email = user_info.get("email")

    result = await db.execute(select(User).where(User.id == reauth_user_id))
    user = result.scalar_one_or_none()

    if not user or user.email != email:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Reauthentication must use the same Google account as your current session.",
        )

    confirm_token = create_delete_confirmation_token(data={"sub": str(user.id)})

    redirect_response = RedirectResponse(url=f"{FRONTEND_URL}/settings/confirm-delete")
    redirect_response.set_cookie(
        key="delete_confirm_token",
        value=confirm_token,
        httponly=True,
        secure=is_production,
        samesite="none" if is_production else "lax",
        max_age=int(DELETE_CONFIRM_TOKEN_EXPIRE.total_seconds()),
    )
    redirect_response.delete_cookie("oauth_state")
    redirect_response.delete_cookie("pkce_verifier")
    redirect_response.delete_cookie("reauth_user_id")

    return redirect_response