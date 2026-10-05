import hashlib
import secrets
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from datetime import datetime, timedelta, timezone
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from uuid import UUID

from app.database import get_db_session
from app.auth import get_current_user
from app.core.email_utils import send_invite_email
from app.models import User, Project, Workspace, Share, Invitation

router = APIRouter(
    prefix="/shares",
    tags=["Sharing"]
)

PENDING = "PENDING"
ACCEPTED = "ACCEPTED"
EXPIRED = "EXPIRED"
REVOKED = "REVOKED"

INVITE_TTL_DAYS = 7


def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode()).hexdigest()


class ShareCreateRequest(BaseModel):
    email: EmailStr


async def get_owned_project(
    db: AsyncSession, workspace_slug: str, project_id: UUID, user: User
) -> Project:
    """Owner-only gate: only the user in projects.created_by_id may share."""
    query = await db.execute(
        select(Project)
        .join(Workspace, Workspace.id == Project.workspace_id)
        .where(Project.id == project_id, Workspace.slug == workspace_slug)
    )
    project = query.scalar_one_or_none()

    if project is None:
        raise HTTPException(status_code=404, detail="Project not found.")

    if project.created_by_id != user.id:
        raise HTTPException(status_code=403, detail="Only the project owner can share this project.")

    return project


# ==========================================
# OWNER: CREATE / LIST / REVOKE
# ==========================================

@router.post("/{workspace_slug}/{project_id}/share", status_code=status.HTTP_201_CREATED)
async def create_share_invitation(
    workspace_slug: str,
    project_id: UUID,
    request: ShareCreateRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    project = await get_owned_project(db, workspace_slug, project_id, current_user)
    invitee_email = request.email.lower()

    if invitee_email == current_user.email.lower():
        raise HTTPException(status_code=400, detail="You cannot share a project with yourself.")

    existing_share = await db.execute(
        select(Share)
        .join(User, User.id == Share.shared_with_id)
        .where(
            Share.project_id == project.id,
            Share.revoked_at.is_(None),
            func.lower(User.email) == invitee_email,
        )
    )
    if existing_share.scalars().first():
        raise HTTPException(status_code=400, detail="This project is already shared with that user.")

    existing_invite = (
        await db.execute(
            select(Invitation).where(
                Invitation.project_id == project.id,
                Invitation.email == invitee_email,
                Invitation.status == PENDING,
            )
        )
    ).scalars().first()

    if existing_invite:
        if datetime.now(timezone.utc) <= existing_invite.expires_at:
            raise HTTPException(status_code=400, detail="A pending invitation already exists for this email.")
        existing_invite.status = EXPIRED
        await db.flush()

    secure_token = secrets.token_urlsafe(32)
    expiration_date = datetime.now(timezone.utc) + timedelta(days=INVITE_TTL_DAYS)

    new_invite = Invitation(
        project_id=project.id,
        project_slug=workspace_slug,
        project_name=project.name,
        email=invitee_email,
        token_hash=_hash_token(secure_token),
        inviter_name=current_user.name,
        invited_by_id=current_user.id,
        status=PENDING,
        expires_at=expiration_date
    )

    db.add(new_invite)

    try:
        await db.flush()
        email_sent = send_invite_email(
            to_email=new_invite.email,
            token=secure_token,
            project_name=project.name,
            inviter_name=current_user.name,
        )

        if not email_sent:
            raise Exception("SMTP Server rejected the payload.")
        await db.commit()

    except Exception:
        await db.rollback()
        raise HTTPException(status_code=500, detail="Failed to dispatch email. Share cancelled.")

    return {"message": "Share invitation sent successfully."}


@router.get("/{workspace_slug}/{project_id}/shares", status_code=status.HTTP_200_OK)
async def list_project_shares(
    workspace_slug: str,
    project_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """Owner-only: pending invites and active shares for a project."""
    project = await get_owned_project(db, workspace_slug, project_id, current_user)

    now = datetime.now(timezone.utc)

    share_rows = (
        await db.execute(
            select(Share, User.email, User.name)
            .join(User, User.id == Share.shared_with_id)
            .where(Share.project_id == project.id, Share.revoked_at.is_(None))
        )
    ).all()


    invite_rows = (
        await db.execute(
            select(Invitation)
            .where(
                Invitation.project_id == project.id,
                Invitation.status.in_([PENDING, EXPIRED]),
            )
            .order_by(Invitation.expires_at.desc())
        )
    ).scalars().all()

    items = [
        {
            "type": "share",
            "id": str(share.id),
            "email": email,
            "name": name,
            "status": ACCEPTED,
            "permission": share.permission,
        }
        for share, email, name in share_rows
    ]

    items += [
        {
            "type": "invitation",
            "id": str(inv.id),
            "email": inv.email,
            "name": None,
            "status": EXPIRED if (inv.status == EXPIRED or now > inv.expires_at) else PENDING,
            "expires_at": inv.expires_at.isoformat(),
        }
        for inv in invite_rows
    ]

    return {"shares": items}


@router.delete("/{workspace_slug}/{project_id}/invitations/{invitation_id}", status_code=status.HTTP_200_OK)
async def revoke_invitation(
    workspace_slug: str,
    project_id: UUID,
    invitation_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """Owner-only: cancels a pending invite so its link stops working."""
    project = await get_owned_project(db, workspace_slug, project_id, current_user)

    invite = (
        await db.execute(
            select(Invitation).where(
                Invitation.id == invitation_id,
                Invitation.project_id == project.id,
            )
        )
    ).scalar_one_or_none()

    if not invite:
        raise HTTPException(status_code=404, detail="Invitation not found.")

    if invite.status != PENDING:
        raise HTTPException(status_code=400, detail=f"This invitation is already {invite.status.lower()}.")

    invite.status = REVOKED
    await db.commit()
    return {"message": "Invitation revoked."}


@router.delete("/{workspace_slug}/{project_id}/shares/{share_id}", status_code=status.HTTP_200_OK)
async def revoke_share(
    workspace_slug: str,
    project_id: UUID,
    share_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """Owner-only: removes access for someone who already accepted."""
    project = await get_owned_project(db, workspace_slug, project_id, current_user)

    share = (
        await db.execute(
            select(Share).where(
                Share.id == share_id,
                Share.project_id == project.id,
            )
        )
    ).scalar_one_or_none()

    if not share:
        raise HTTPException(status_code=404, detail="Share not found.")

    if share.revoked_at is not None:
        raise HTTPException(status_code=400, detail="This share is already revoked.")

    share.revoked_at = datetime.now(timezone.utc)
    await db.commit()
    return {"message": "Access revoked."}


@router.post("/{workspace_slug}/{project_id}/invitations/{invitation_id}/resend", status_code=status.HTTP_200_OK)
async def resend_invitation(
    workspace_slug: str,
    project_id: UUID,
    invitation_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """
    Owner-only: re-sends a PENDING or EXPIRED invite.
    """
    project = await get_owned_project(db, workspace_slug, project_id, current_user)

    invite = (
        await db.execute(
            select(Invitation)
            .where(Invitation.id == invitation_id, Invitation.project_id == project.id)
            .with_for_update()
        )
    ).scalar_one_or_none()

    if not invite:
        raise HTTPException(status_code=404, detail="Invitation not found.")

    if invite.status not in (PENDING, EXPIRED):
        raise HTTPException(status_code=400, detail=f"This invitation is already {invite.status.lower()}.")

    other_live = (
        await db.execute(
            select(Invitation).where(
                Invitation.project_id == project.id,
                Invitation.email == invite.email,
                Invitation.status == PENDING,
                Invitation.expires_at > datetime.now(timezone.utc),
                Invitation.id != invite.id,
            )
        )
    ).scalars().first()
    if other_live:
        raise HTTPException(status_code=400, detail="A pending invitation already exists for this email.")

    already_shared = (
        await db.execute(
            select(Share)
            .join(User, User.id == Share.shared_with_id)
            .where(
                Share.project_id == project.id,
                Share.revoked_at.is_(None),
                func.lower(User.email) == invite.email.lower(),
            )
        )
    ).scalars().first()
    if already_shared:
        raise HTTPException(status_code=400, detail="This project is already shared with that user.")

    secure_token = secrets.token_urlsafe(32)
    invite.token_hash = _hash_token(secure_token)
    invite.status = PENDING
    invite.expires_at = datetime.now(timezone.utc) + timedelta(days=INVITE_TTL_DAYS)

    try:
        await db.flush()
        email_sent = send_invite_email(
            to_email=invite.email,
            token=secure_token,
            project_name=project.name,
            inviter_name=current_user.name,
        )

        if not email_sent:
            raise Exception("SMTP Server rejected the payload.")
        await db.commit()

    except Exception:
        await db.rollback()
        raise HTTPException(status_code=500, detail="Failed to dispatch email. Invitation unchanged.")

    return {"message": "Invitation resent successfully."}


# ==========================================
# INVITEE: DETAILS / ACCEPT
# ==========================================

@router.get("/{token}", status_code=status.HTTP_200_OK)
async def get_share_invitation_details(token: str, db: AsyncSession = Depends(get_db_session)):
    """Unauthenticated: lets the invite page render before the user logs in."""
    query = await db.execute(select(Invitation).where(Invitation.token_hash == _hash_token(token)))
    invite = query.scalar_one_or_none()

    if not invite:
        raise HTTPException(status_code=404, detail="Invitation not found.")

    if invite.status == PENDING and datetime.now(timezone.utc) > invite.expires_at:
        invite.status = EXPIRED
        await db.commit()

    if invite.status != PENDING:
        raise HTTPException(status_code=400, detail=f"This invitation is already {invite.status.lower()}.")

    return {
        "project_name": invite.project_name,
        "inviter_name": invite.inviter_name,
        "email": invite.email
    }


@router.post("/{token}/accept", status_code=status.HTTP_200_OK)
async def accept_share_invitation(
    token: str,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user)
):
    query = await db.execute(
        select(Invitation).where(Invitation.token_hash == _hash_token(token)).with_for_update()
    )
    invite = query.scalar_one_or_none()

    if not invite or invite.status != PENDING:
        raise HTTPException(status_code=400, detail="Invalid or inactive invitation.")

    if datetime.now(timezone.utc) > invite.expires_at:
        invite.status = EXPIRED
        await db.commit()
        raise HTTPException(status_code=400, detail="This invitation has expired.")

    if current_user.email.lower() != invite.email.lower():
        raise HTTPException(
            status_code=403,
            detail="You must be logged in with the exact email address this invitation was sent to."
        )

    existing_share = (
        await db.execute(
            select(Share).where(
                Share.project_id == invite.project_id,
                Share.shared_with_id == current_user.id,
                Share.revoked_at.is_(None),
            )
        )
    ).scalars().first()
    if existing_share:
        raise HTTPException(status_code=400, detail="You already have access to this project.")

    db.add(Share(
        project_id=invite.project_id,
        shared_by_id=invite.invited_by_id,
        shared_with_id=current_user.id,
        permission="view"
    ))
    await db.flush()

    row = (
        await db.execute(
            select(Project, Workspace.slug)
            .join(Workspace, Workspace.id == Project.workspace_id)
            .where(Project.id == invite.project_id)
        )
    ).first()
    if not row:
        await db.rollback()
        raise HTTPException(status_code=404, detail="Project no longer exists.")

    project, owner_workspace_slug = row

    if project.created_by_id == current_user.id:
        await db.rollback()
        raise HTTPException(status_code=400, detail="You already own this project.")

    invite.status = ACCEPTED

    await db.commit()

    return {
        "message": "Project shared with you!",
        "project_id": str(invite.project_id),
        "workspace_slug": owner_workspace_slug
    }