import secrets

from fastapi import APIRouter, Depends, HTTPException, status

from pydantic import BaseModel, Field
from typing import List
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.database import get_db_session
from app.auth import get_current_user
from app.models import User, Workspace

from app.core.utils import generate_slug

router = APIRouter(
    prefix="/workspaces",
    tags=["Workspace Management"],
    dependencies=[Depends(get_current_user)]
)


class WorkspaceCreationRequest(BaseModel):
    workspace_name: str = Field(min_length=1, max_length=100)


class WorkspaceRenameRequest(BaseModel):
    new_name: str = Field(min_length=1, max_length=100)


class WorkspaceResponse(BaseModel):
    workspace_name: str
    workspace_slug: str


async def _unique_slug(db: AsyncSession, name: str) -> str:
    base_slug = generate_slug(name)
    slug = base_slug

    while True:
        existing = (await db.execute(select(Workspace).where(Workspace.slug == slug))).scalar_one_or_none()
        if not existing:
            return slug
        slug = f"{base_slug}-{secrets.token_hex(2)}"


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_workspace(
    request: WorkspaceCreationRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """
    Creates an additional workspace for the user (users can own several).
    """
    workspace_slug = await _unique_slug(db, request.workspace_name)

    new_workspace = Workspace(
        name=request.workspace_name,
        slug=workspace_slug,
        owner_id=current_user.id,
        last_used_at=datetime.now(timezone.utc),
    )
    db.add(new_workspace)
    await db.commit()

    return {
        "message": "Workspace created successfully.",
        "workspace_name": request.workspace_name,
        "workspace_slug": workspace_slug,
    }


@router.get("/", response_model=List[WorkspaceResponse], status_code=status.HTTP_200_OK)
async def get_user_workspaces(
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user)
):
    """
    Fetches all workspaces owned by the currently authenticated user.
    """
    query = (
        select(Workspace.name, Workspace.slug)
        .where(Workspace.owner_id == current_user.id)
    )
    result = await db.execute(query)
    rows = result.all()
    return [
        WorkspaceResponse(workspace_name=row.name, workspace_slug=row.slug)
        for row in rows if row.slug is not None
    ]


@router.patch("/{workspace_slug}/name", status_code=status.HTTP_200_OK)
async def update_workspace_name(
    workspace_slug: str,
    request: WorkspaceRenameRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user)
):
    """
    Renames the user's workspace and updates its slug.
    """
    target_query = await db.execute(
        select(Workspace).where(Workspace.owner_id == current_user.id, Workspace.slug == workspace_slug)
    )
    target_workspace = target_query.scalar_one_or_none()

    if not target_workspace:
        raise HTTPException(status_code=404, detail="This workspace does not exist for user")

    target_workspace.name = request.new_name
    target_workspace.slug = await _unique_slug(db, request.new_name)

    await db.commit()
    return {
        "message": "Workspace name updated successfully.",
        "workspace_slug": target_workspace.slug,
    }


@router.patch("/{workspace_slug}/last-used", status_code=status.HTTP_200_OK)
async def mark_workspace_used(
    workspace_slug: str,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """Records the workspace as most recently used, for the next login redirect."""
    target_query = await db.execute(
        select(Workspace).where(Workspace.owner_id == current_user.id, Workspace.slug == workspace_slug)
    )
    target_workspace = target_query.scalar_one_or_none()

    if not target_workspace:
        raise HTTPException(status_code=404, detail="This workspace does not exist for user")

    target_workspace.last_used_at = datetime.now(timezone.utc)
    await db.commit()
    return {"message": "Workspace marked as last used."}

@router.delete("/{workspace_slug}", status_code=status.HTTP_200_OK)
async def delete_workspace(
    workspace_slug: str,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """
    Permanently deletes a workspace the user owns, along with its contents.
    """
    target_query = await db.execute(
        select(Workspace).where(Workspace.owner_id == current_user.id, Workspace.slug == workspace_slug)
    )
    target_workspace = target_query.scalar_one_or_none()

    if not target_workspace:
        raise HTTPException(status_code=404, detail="This workspace does not exist for user")

    await db.delete(target_workspace)
    await db.commit()
    return {"message": "Workspace deleted successfully."}   