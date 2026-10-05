from datetime import datetime
from typing import Annotated, List, Literal, Optional, Tuple
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, StringConstraints
from sqlalchemy import delete, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.auth import get_current_user
from app.database import get_db_session
from app.models import Project, Share, Tree, User, Workspace
from app.project_forking import get_user_copy

router = APIRouter(
    prefix="/projects",
    tags=["Projects Management"],
    dependencies=[Depends(get_current_user)],
)

ProjectName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class ProjectSummary(BaseModel):
    id: UUID
    project_name: str
    role: Literal["owner", "shared"]
    created_at: datetime
    workspace_id: UUID
    workspace_slug: str
    forked_from_project_id: Optional[UUID] = None
    forked_project_id: Optional[UUID] = None


class ProjectDetail(ProjectSummary):
    tree_count: int


class ProjectCreate(BaseModel):
    project_name: ProjectName
    workspace_id: UUID


class ProjectRename(BaseModel):
    project_name: ProjectName


def _active_share_for(user_id: UUID):
    return (
        Share.shared_with_id == user_id,
        Share.revoked_at.is_(None),
    )


def _summary(
    project: Project,
    role: str,
    workspace_slug: str,
    forked_project_id: Optional[UUID] = None,
) -> ProjectSummary:
    return ProjectSummary(
        id=project.id,
        project_name=project.name,
        role=role,
        created_at=project.created_at,
        workspace_id=project.workspace_id,
        workspace_slug=workspace_slug,
        forked_from_project_id=project.forked_from_project_id,
        forked_project_id=forked_project_id,
    )


async def _workspace_slug(db: AsyncSession, workspace_id: UUID) -> str:
    slug = (
        await db.execute(select(Workspace.slug).where(Workspace.id == workspace_id))
    ).scalar_one_or_none()
    if slug is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workspace not found!")
    return slug


async def get_project_with_role(
    db: AsyncSession, project_id: UUID, user: User
) -> Tuple[Project, Literal["owner", "shared"]]:
    project = (
        await db.execute(select(Project).where(Project.id == project_id))
    ).scalar_one_or_none()

    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found!")

    if project.created_by_id == user.id:
        return project, "owner"

    share_id = (
        await db.execute(
            select(Share.id).where(Share.project_id == project_id, *_active_share_for(user.id)).limit(1)
        )
    ).scalar_one_or_none()

    if share_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found!")

    return project, "shared"


async def require_owner(db: AsyncSession, project_id: UUID, user: User) -> Project:
    project, role = await get_project_with_role(db, project_id, user)
    if role != "owner":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the project owner can do this!")
    return project


async def _name_taken(
    db: AsyncSession,
    user_id: UUID,
    workspace_id: UUID,
    name: str,
    exclude_id: Optional[UUID] = None,
) -> bool:
    query = select(Project.id).where(
        Project.created_by_id == user_id,
        Project.workspace_id == workspace_id,
        Project.name == name,
    )
    if exclude_id is not None:
        query = query.where(Project.id != exclude_id)
    return (await db.execute(query.limit(1))).scalar_one_or_none() is not None


@router.get("/", response_model=List[ProjectSummary])
async def list_projects(
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    owned_rows = (
        await db.execute(
            select(Project, Workspace.slug)
            .join(Workspace, Workspace.id == Project.workspace_id)
            .where(Project.created_by_id == current_user.id)
            .order_by(Project.created_at.desc())
        )
    ).all()

    shared_rows = (
        await db.execute(
            select(Project, Workspace.slug)
            .join(Workspace, Workspace.id == Project.workspace_id)
            .join(Share, Share.project_id == Project.id)
            .where(*_active_share_for(current_user.id))
            .order_by(Project.created_at.desc())
        )
    ).all()

    result = [_summary(p, "owner", slug) for p, slug in owned_rows]

    hidden = {p.id for p, _ in owned_rows}
    hidden.update(p.forked_from_project_id for p, _ in owned_rows if p.forked_from_project_id)

    for project, slug in shared_rows:
        if project.id in hidden:
            continue
        hidden.add(project.id)
        result.append(_summary(project, "shared", slug))

    return result


@router.get("/{project_id}", response_model=ProjectDetail)
async def get_project(
    project_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    project, role = await get_project_with_role(db, project_id, current_user)
    slug = await _workspace_slug(db, project.workspace_id)

    tree_count = (
        await db.execute(select(func.count()).select_from(Tree).where(Tree.project_id == project.id))
    ).scalar_one()

    forked_project_id = None
    if role == "shared":
        user_copy = await get_user_copy(db, project.id, current_user.id)
        forked_project_id = user_copy.id if user_copy else None

    return ProjectDetail(
        **_summary(project, role, slug, forked_project_id).model_dump(),
        tree_count=tree_count,
    )


@router.post("/", response_model=ProjectSummary, status_code=status.HTTP_201_CREATED)
async def create_project(
    body: ProjectCreate,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    slug = (
        await db.execute(
            select(Workspace.slug).where(
                Workspace.id == body.workspace_id,
                Workspace.owner_id == current_user.id,
            )
        )
    ).scalar_one_or_none()

    if slug is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workspace not found!")

    if await _name_taken(db, current_user.id, body.workspace_id, body.project_name):
        raise HTTPException(status.HTTP_409_CONFLICT, "A project with this name already exists in this workspace.")

    new_project = Project(
        name=body.project_name,
        workspace_id=body.workspace_id,
        created_by_id=current_user.id,
    )

    db.add(new_project)
    await db.flush()
    await db.refresh(new_project)
    await db.commit()

    return _summary(new_project, "owner", slug)


@router.patch("/{project_id}", response_model=ProjectSummary)
async def rename_project(
    project_id: UUID,
    body: ProjectRename,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    project = await require_owner(db, project_id, current_user)

    if await _name_taken(db, current_user.id, project.workspace_id, body.project_name, exclude_id=project.id):
        raise HTTPException(status.HTTP_409_CONFLICT, "A project with this name already exists in this workspace.")

    slug = await _workspace_slug(db, project.workspace_id)
    project.name = body.project_name
    await db.commit()
    await db.refresh(project)

    return _summary(project, "owner", slug)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    await require_owner(db, project_id, current_user)
    await db.execute(delete(Project).where(Project.id == project_id))
    await db.commit()