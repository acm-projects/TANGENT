from datetime import datetime
from uuid import UUID
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

Role = Literal["user", "assistant"]


class ChatMessage(BaseModel):
    """One element of nodes.chats (JSON array)."""

    role: Role
    content: str
    seq: int  # redundant with array index; flatten trusts array order
    created_at: datetime


class PathNode(BaseModel):
    """One node row in the ancestor graph returned by the recursive CTE."""

    id: str
    chats: list[ChatMessage]
    model: Optional[str] = None
    parent_id: Optional[str] = None
    title: Optional[str] = None
    created_at: Optional[datetime] = None
    merge_source_ids: list[str] = Field(default_factory=list)


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