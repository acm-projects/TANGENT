from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel

Role = Literal["user", "assistant"]
BranchSource = Literal["a", "b"]


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
