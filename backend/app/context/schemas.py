from datetime import datetime
from uuid import UUID
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict

Role = Literal["user", "assistant"]
BranchSource = str  # merge copies are tagged with the source leaf node id (nodes_router.merge_nodes)


class ChatMessage(BaseModel):
    """One element of nodes.chats (JSON array)."""

    role: Role
    content: str
    seq: int  # redundant with array index; flatten trusts array order
    branch_source: Optional[BranchSource] = None  # set only on merge-copied messages
    created_at: datetime


class PathNode(BaseModel):
    """One ancestor row as returned by the recursive CTE, root -> leaf order."""

    id: str
    chats: list[ChatMessage]
    model: Optional[str] = None


# --- GET /trees/:id, GET /nodes/:id (mirrors frontend/src/api/types.ts) -------------------------
class NodeMeta(BaseModel):
    """Structure only, no chats, so the whole tree loads cheaply for the mind map."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tree_id: UUID
    project_id: UUID
    parent_id: Optional[UUID] = None  # None iff root
    fork_index: int
    node_type: Optional[str] = None
    status: str
    title: Optional[str] = None
    summary: Optional[str] = None
    model: Optional[str] = None
    tokens: int
    created_by_id: UUID
    created_at: datetime
    # a merged node's two source leaves (node_merge_sources); filled in by the tree endpoints only
    merge_source_ids: list[UUID] = []


class NodeOut(NodeMeta):
    chats: list[ChatMessage]


class TreeMeta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    root_node_id: Optional[UUID] = None
    created_at: datetime


class TreeOut(BaseModel):
    tree: TreeMeta
    nodes: list[NodeMeta]