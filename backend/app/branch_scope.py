"""Branch-only shares: a sharee sees the shared node and every ancestor through either merge parent.
Sibling branches and anything below the shared node stay hidden.

RLS (has_project_access) only knows project-level access, so the scoping is enforced here, by the
endpoints that read or copy nodes for a sharee."""
from uuid import UUID

from fastapi import HTTPException

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models import Project, Share

_PATH_IDS_SQL = text("""
    WITH RECURSIVE path(id) AS (
      SELECT CAST(:node AS uuid)
      UNION
      SELECT e.parent
      FROM path p
      JOIN (
        SELECT id AS child, parent_id AS parent FROM nodes WHERE parent_id IS NOT NULL
        UNION ALL
        SELECT node_id, source_leaf_id FROM node_merge_sources
      ) e ON e.child = p.id
    )
    SELECT id FROM path
""")


async def branch_root(db: AsyncSession, project_id: UUID, user_id: UUID) -> UUID | None:
    """The node the caller's access ends at, or None for full access (owner, a whole-project share,
    or no share row at all, where RLS decides). Branch shares are one per user per project."""
    project = await db.get(Project, project_id)
    if project is None or project.created_by_id == user_id:
        return None
    roots = (
        await db.execute(
            select(Share.branch_node_id).where(
                Share.project_id == project_id,
                Share.shared_with_id == user_id,
                Share.revoked_at.is_(None),
            )
        )
    ).scalars().all()
    if not roots or None in roots:
        return None
    return roots[0]


async def visible_ids(db: AsyncSession, node: UUID) -> set[UUID]:
    """The shared node and its ancestors through both kinds of parent link."""
    return {r.id for r in (await db.execute(_PATH_IDS_SQL, {"node": node})).all()}


async def visible_to(db: AsyncSession, project_id: UUID, user_id: UUID) -> set[UUID] | None:
    """The node ids the caller may see in this project, or None for all of them."""
    root = await branch_root(db, project_id, user_id)
    return None if root is None else await visible_ids(db, root)


async def require_visible(db: AsyncSession, project_id: UUID, user_id: UUID, *node_ids: UUID) -> None:
    """404 for a node outside the caller's shared branch: the same answer as for a node that doesn't exist."""
    visible = await visible_to(db, project_id, user_id)
    if visible is not None and not set(node_ids) <= visible:
        raise HTTPException(404, "Node not found")
