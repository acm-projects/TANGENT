"""POST /projects/{id}/agent: a test bench for the agent tools. One request runs the whole tool loop and returns
the final reply plus a log of the calls it made. Not streamed, not saved: the client keeps the conversation."""

import asyncio
import json
import logging
from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent import tools
from app.auth import get_current_user
from app.core.openrouter import DEFAULT_MODEL_ID, get_model_or_400, stream_openrouter
from app.database import get_db_session
from app.models import User
from app.papers import service as paper_service
from app.routers.projects_router import get_project_with_role

log = logging.getLogger(__name__)
router = APIRouter(prefix="/projects", tags=["Agent"])

MAX_ROUNDS = 6  # model turns that may call tools; the next one must answer
MAX_CALLS_PER_ROUND = 5
TOOL_TIMEOUT = 30

SYSTEM_PROMPT = """You are Tangent's research agent. You work on the user's project tree through tools: you can read, search, \
branch, merge and delete nodes, and search the project's sources. Do what the user asks with the tools, then say briefly what you did.

- Use the node ids below. Never invent an id; if a node the user names is not listed, call search_nodes.
- Calls run in order. When one needs the result of another (merge the node you just created), make it in a later turn.
- "that" and "it" mean the node you most recently created or discussed in this conversation.
- A tool error is information: report it plainly and do not retry the same call.
- Deleting is permanent. Delete exactly the node asked for, nothing else.

The user currently has this node selected: {active}

Nodes in this project:
{outline}"""


class AgentMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=20_000)


class AgentRequest(BaseModel):
    messages: list[AgentMessage] = Field(min_length=1, max_length=40)
    model: str = DEFAULT_MODEL_ID
    active_node_id: Optional[UUID] = None


class ToolCallLog(BaseModel):
    name: str
    arguments: dict
    result: dict


class AgentReply(BaseModel):
    reply: str
    tool_calls: list[ToolCallLog]
    model: str


async def _run(call: dict, project_id: UUID, user_id: UUID) -> tuple[dict, dict]:
    """One tool call from the model -> (its arguments, its result). Failures become results the model can read."""
    try:
        args = json.loads(call["function"]["arguments"] or "{}")
    except ValueError:
        return {}, {"error": "The tool arguments were not valid JSON."}
    try:
        return args, await asyncio.wait_for(tools.call_tool(call["function"]["name"], args, project_id, user_id), TOOL_TIMEOUT)
    except asyncio.TimeoutError:
        return args, {"error": "The tool timed out."}


@router.post("/{project_id}/agent", response_model=AgentReply)
async def agent_chat(
    project_id: UUID,
    req: AgentRequest,
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
):
    get_model_or_400(req.model)
    await get_project_with_role(db, project_id, user)
    user_id = user.id  # read before rollback: it expires `user`, and a lazy reload here raises MissingGreenlet
    await db.rollback()  # release the request's connection before the model call
    active = str(req.active_node_id) if req.active_node_id else "none"
    convo: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT.format(active=active, outline=await tools.outline(project_id, user_id))},
        *({"role": m.role, "content": m.content} for m in req.messages),
    ]
    logged: list[ToolCallLog] = []

    for round_ in range(MAX_ROUNDS):
        text, calls = "", []
        async for event in stream_openrouter(
            convo, req.model, tools=tools.AGENT_TOOLS, tool_choice="none" if round_ == MAX_ROUNDS - 1 else None
        ):
            if "error" in event:
                raise HTTPException(502, f"The model failed: {event['error']}")
            text += event.get("text", "")
            calls = event.get("tool_calls", calls)
        if not calls and paper_service.LEAK_MARKER in text:  # some models write the call as text
            calls = paper_service.parse_leaked_tool_calls(text)
            text = text.split(paper_service.LEAK_MARKER)[0]
        if not calls:
            return AgentReply(reply=text.strip(), tool_calls=logged, model=req.model)

        convo.append({"role": "assistant", "content": text or None, "tool_calls": calls})
        for i, call in enumerate(calls):
            if i >= MAX_CALLS_PER_ROUND:
                args, result = {}, {"error": f"At most {MAX_CALLS_PER_ROUND} tool calls at once; this one was skipped."}
            else:
                args, result = await _run(call, project_id, user_id)
            logged.append(ToolCallLog(name=call["function"]["name"], arguments=args, result=result))
            convo.append({"role": "tool", "tool_call_id": call["id"], "content": json.dumps(result, default=str)})

    raise HTTPException(502, "The agent did not finish")  # unreachable: the last round forbids tool calls
