from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import defer

from app.auth import get_current_user
from app.context.schemas import NodeMeta, TreeMeta, TreeOut
from app.database import get_db_session
from app.models import Node, NodeMergeSource, Project, Tree, User

router = APIRouter(tags=["Trees"], dependencies=[Depends(get_current_user)])


async def _tree_out(db: AsyncSession, tree: Tree) -> TreeOut:
    nodes = (
        await db.execute(
            select(Node).where(Node.tree_id == tree.id).order_by(Node.created_at).options(defer(Node.chats))
        )
    ).scalars().all()
    sources: dict[UUID, list[UUID]] = {}
    rows = await db.execute(
        select(NodeMergeSource.node_id, NodeMergeSource.source_leaf_id)
        .join(Node, Node.id == NodeMergeSource.node_id)
        .where(Node.tree_id == tree.id)
    )
    for merged_id, source_id in rows:
        sources.setdefault(merged_id, []).append(source_id)
    return TreeOut(
        tree=TreeMeta.model_validate(tree),
        nodes=[NodeMeta.model_validate(n).model_copy(update={"merge_source_ids": sources.get(n.id, [])}) for n in nodes],
    )


@router.get("/trees/{tree_id}", response_model=TreeOut)
async def get_tree(tree_id: UUID, db: AsyncSession = Depends(get_db_session)):
    tree = await db.get(Tree, tree_id)  # RLS hides trees of projects the caller can't see
    if tree is None:
        raise HTTPException(404, "Tree not found")
    return await _tree_out(db, tree)


@router.get("/projects/{project_id}/tree", response_model=TreeOut)
async def get_project_tree(
    project_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
):
    """The project's tree. Nothing creates a tree when a project is created, so the owner's first
    visit makes it (one empty root node). A sharee never creates: they see nothing until the owner has."""
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(404, "Project not found")

    first_tree = select(Tree).where(Tree.project_id == project_id).order_by(Tree.created_at).limit(1)
    tree = (await db.execute(first_tree)).scalar_one_or_none()

    if tree is None:
        if project.created_by_id != user.id:
            raise HTTPException(404, "Project not found")
        # Row lock: a second simultaneous first visit waits here, then sees the tree the first one made.
        await db.execute(select(Project.id).where(Project.id == project_id).with_for_update())
        tree = (await db.execute(first_tree)).scalar_one_or_none()
    if tree is None:
        tree = Tree(project_id=project_id, created_by_id=user.id)
        db.add(tree)
        await db.flush()
        root = Node(tree_id=tree.id, project_id=project_id, parent_id=None, fork_index=0, created_by_id=user.id)
        db.add(root)
        await db.flush()
        tree.root_node_id = root.id
        await db.commit()
        await db.refresh(tree)

    return await _tree_out(db, tree)
