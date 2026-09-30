"""
Context reconstruction: ancestor path (root -> leaf) -> LLM messages.

Fetch the path with one query; flatten() is pure so it can be unit-tested without a DB.

    WITH RECURSIVE path AS (
      SELECT id, parent_id, chats, 0 AS depth FROM nodes WHERE id = :leaf_id
      UNION ALL
      SELECT n.id, n.parent_id, n.chats, p.depth + 1
      FROM nodes n JOIN path p ON n.id = p.parent_id
    )
    SELECT id, chats FROM path ORDER BY depth DESC;   -- root first

The endpoint must also reject prompts to non-leaf nodes (enforce the invariant
server-side, not just in the UI).
"""

from dataclasses import dataclass
from typing import Sequence

from schemas import ChatMessage, PathNode


@dataclass(frozen=True)
class LLMMessage:
    role: str
    content: str


@dataclass(frozen=True)
class Segment:
    """Messages contributed by one node. Node boundaries are the natural
    prompt-cache breakpoints, so they are preserved until the final payload step."""

    node_id: str
    messages: tuple[LLMMessage, ...]


def _render_branches(branches: dict[str, list[ChatMessage]]) -> str:
    parts = ["The user merged two conversation branches into this one. Both transcripts follow."]
    for key in ("a", "b"):
        msgs = branches[key]
        if not msgs:
            continue
        body = "\n\n".join(f"{m.role.capitalize()}: {m.content}" for m in msgs)
        parts.append(f"<branch_{key}>\n{body}\n</branch_{key}>")
    return "\n\n".join(parts)


def _serialize_node(chats: Sequence[ChatMessage]) -> tuple[LLMMessage, ...]:
    branches: dict[str, list[ChatMessage]] = {"a": [], "b": []}
    for m in chats:
        if m.branch_source:
            branches[m.branch_source].append(m)

    out: list[LLMMessage] = []
    branch_block_emitted = False
    for m in chats:  # array order is the order; seq is not consulted
        if m.branch_source is None:
            out.append(LLMMessage(m.role, m.content))
        elif not branch_block_emitted:
            # Both snapshots collapse into ONE user turn at the position of the
            # first tagged message. Replaying them as alternating turns would
            # interleave two conversations and break role alternation.
            out.append(LLMMessage("user", _render_branches(branches)))
            branch_block_emitted = True
    return tuple(out)


def flatten(path: Sequence[PathNode]) -> list[Segment]:
    """path must be ordered root -> leaf."""
    return [Segment(n.id, _serialize_node(n.chats)) for n in path if n.chats]


def to_provider_messages(segments: Sequence[Segment], new_user_message: str) -> list[dict]:
    """Segments -> provider payload. Coalesces adjacent same-role messages
    (e.g. merge block followed by the user's first prompt on the merge node)."""
    flat = [m for s in segments for m in s.messages]
    flat.append(LLMMessage("user", new_user_message))

    out: list[dict] = []
    for m in flat:
        if out and out[-1]["role"] == m.role:
            out[-1]["content"] += "\n\n" + m.content
        else:
            out.append({"role": m.role, "content": m.content})
    return out
