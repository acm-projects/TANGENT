import copy
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models import Node, NodeMergeSource, Project, Share, Tree, Workspace


@dataclass
class ForkResult:
    project: Project
    tree_map: Dict[UUID, UUID] = field(default_factory=dict)
    node_map: Dict[UUID, UUID] = field(default_factory=dict)


def copy_exists_error(copy_id: UUID) -> HTTPException:
    return HTTPException(
        status.HTTP_409_CONFLICT,
        detail={
            "message": "You already have your own copy of this project. Edit that one.",
            "forked_project_id": str(copy_id),
        },
    )


async def get_user_copy(
    db: AsyncSession, original_project_id: UUID, user_id: UUID
) -> Optional[Project]:
    return (
        await db.execute(
            select(Project).where(
                Project.created_by_id == user_id,
                Project.forked_from_project_id == original_project_id,
            )
        )
    ).scalar_one_or_none()


async def pick_workspace_id(db: AsyncSession, user_id: UUID) -> UUID:
    workspace_id = (
        await db.execute(
            select(Workspace.id)
            .where(Workspace.owner_id == user_id)
            .order_by(Workspace.last_used_at.desc().nulls_last(), Workspace.created_at)
            .limit(1)
        )
    ).scalar_one_or_none()
    if workspace_id is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "You need a workspace before you can edit a shared project.",
        )
    return workspace_id


async def _copy_project(
    db: AsyncSession, original: Project, new_owner_id: UUID, workspace_id: UUID
) -> ForkResult:
    new_project = Project(
        id=uuid4(),
        workspace_id=workspace_id,
        name=original.name,
        created_by_id=new_owner_id,
        forked_from_project_id=original.id,
    )
    db.add(new_project)
    await db.flush()

    trees = (
        await db.execute(select(Tree).where(Tree.project_id == original.id))
    ).scalars().all()
    nodes = (
        await db.execute(select(Node).where(Node.project_id == original.id))
    ).scalars().all()

    tree_map = {t.id: uuid4() for t in trees}
    node_map = {n.id: uuid4() for n in nodes}

    new_trees: Dict[UUID, Tree] = {}
    for t in trees:
        nt = Tree(
            id=tree_map[t.id],
            project_id=new_project.id,
            created_by_id=new_owner_id,
            created_at=t.created_at,
        )
        new_trees[t.id] = nt
        db.add(nt)
    await db.flush()

    children = defaultdict(list)
    queue = deque()
    for n in nodes:
        if n.parent_id in node_map:
            children[n.parent_id].append(n)
        else:
            queue.append(n)

    while queue:
        n = queue.popleft()
        db.add(
            Node(
                id=node_map[n.id],
                tree_id=tree_map[n.tree_id],
                project_id=new_project.id,
                parent_id=node_map.get(n.parent_id),
                fork_index=n.fork_index,
                node_type=n.node_type,
                status=n.status,
                title=n.title,
                summary=n.summary,
                chats=copy.deepcopy(n.chats),
                created_by_id=new_owner_id,
                created_at=n.created_at,
            )
        )
        queue.extend(children[n.id])
    await db.flush()

    if node_map:
        merges = (
            await db.execute(
                select(NodeMergeSource).where(NodeMergeSource.node_id.in_(list(node_map)))
            )
        ).scalars().all()
        for m in merges:
            if m.source_leaf_id in node_map:
                db.add(
                    NodeMergeSource(
                        node_id=node_map[m.node_id],
                        source_leaf_id=node_map[m.source_leaf_id],
                    )
                )

    for t in trees:
        nt = new_trees[t.id]
        nt.root_node_id = node_map.get(t.root_node_id)
        nt.forked_from_tree_id = tree_map.get(t.forked_from_tree_id)
        nt.forked_from_node_id = node_map.get(t.forked_from_node_id)
    await db.flush()

    return ForkResult(project=new_project, tree_map=tree_map, node_map=node_map)


async def duplicate_project_for_user(
    db: AsyncSession,
    original_project_id: UUID,
    new_owner_id: UUID,
    workspace_id: Optional[UUID] = None,
) -> ForkResult:
    existing = await get_user_copy(db, original_project_id, new_owner_id)
    if existing is not None:
        raise copy_exists_error(existing.id)

    original = (
        await db.execute(select(Project).where(Project.id == original_project_id))
    ).scalar_one_or_none()
    if original is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found!")

    if workspace_id is None:
        workspace_id = await pick_workspace_id(db, new_owner_id)

    try:
        async with db.begin_nested():
            return await _copy_project(db, original, new_owner_id, workspace_id)
    except IntegrityError:
        existing = await get_user_copy(db, original_project_id, new_owner_id)
        if existing is not None:
            raise copy_exists_error(existing.id)
        raise


async def get_write_target(
    db: AsyncSession, project_id: UUID, user_id: UUID
) -> Tuple[UUID, Optional[ForkResult]]:
    project = (
        await db.execute(select(Project).where(Project.id == project_id))
    ).scalar_one_or_none()
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found!")

    if project.created_by_id == user_id:
        return project.id, None

    share_id = (
        await db.execute(
            select(Share.id)
            .where(
                Share.project_id == project_id,
                Share.shared_with_id == user_id,
                Share.revoked_at.is_(None),
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if share_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found!")

    result = await duplicate_project_for_user(db, project_id, user_id)
    return result.project.id, result