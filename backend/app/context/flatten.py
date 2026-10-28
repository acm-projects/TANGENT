"""Render a graph reading plan as model messages."""

from dataclasses import dataclass
from typing import Mapping, Sequence

from app.context.plan import PlanItem
from app.context.schemas import PathNode


@dataclass(frozen=True)
class LLMMessage:
    role: str
    content: str


@dataclass(frozen=True)
class Segment:
    """Messages contributed by one node or one top-level merge block."""

    node_id: str | None
    messages: tuple[LLMMessage, ...]


def _branch_title(node_id: str, nodes: Mapping[str, PathNode]) -> str:
    title = nodes[node_id].title if node_id in nodes else None
    return (title or "").replace('"', "") or "Untitled branch"


def _branch_markup(source: str, plan: Sequence[PlanItem], nodes: Mapping[str, PathNode]) -> str:
    body: list[str] = []
    for item in plan:
        if isinstance(item, str):
            node = nodes[item]
            body.extend(f"{message.role.capitalize()}: {message.content}" for message in node.chats)
        else:
            body.append(_nested_merge(item["merge"], nodes))
    return f'<branch from="{_branch_title(source, nodes)}">\n' + "\n".join(body) + "\n</branch>"


def _nested_merge(branches: Sequence[dict], nodes: Mapping[str, PathNode]) -> str:
    return "<merge>\n" + "\n".join(
        _branch_markup(branch["from"], branch["plan"], nodes) for branch in branches
    ) + "\n</merge>"


def flatten(plan: Sequence[PlanItem], nodes: Mapping[str, PathNode]) -> list[Segment]:
    """Render card messages and merge blocks in the supplied reading order."""
    segments: list[Segment] = []
    for item in plan:
        if isinstance(item, str):
            node = nodes[item]
            messages = tuple(LLMMessage(message.role, message.content) for message in node.chats)
            if messages:
                segments.append(Segment(item, messages))
            continue

        branches = item["merge"]
        content = (
            "The user merged these branches of the conversation into this one. "
            "Each branch continues from the conversation above.\n\n"
            + "\n".join(_branch_markup(branch["from"], branch["plan"], nodes) for branch in branches)
        )
        segments.append(Segment(None, (LLMMessage("user", content),)))
    return segments


def to_provider_messages(segments: Sequence[Segment], new_user_message: str) -> list[dict]:
    """Coalesce adjacent same-role messages into the provider payload."""
    flat = [message for segment in segments for message in segment.messages]
    flat.append(LLMMessage("user", new_user_message))

    out: list[dict] = []
    for message in flat:
        if out and out[-1]["role"] == message.role:
            out[-1]["content"] += "\n\n" + message.content
        else:
            out.append({"role": message.role, "content": message.content})
    return out
