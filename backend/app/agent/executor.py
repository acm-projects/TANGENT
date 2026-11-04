"""Runs research tools for the loop through tools.call_tool, with a write-ahead record in agent_executions so a
restart can tell what was in flight. Tools never raise (call_tool returns {"error": ...}); a timeout is an error result."""

import asyncio
from uuid import UUID

from app.agent import ops, store, tools

TOOL_TIMEOUT = 30
ASK_TIMEOUT = 120  # ask_node waits for a whole model reply
TIMED_OUT = {"error": "The tool timed out."}


async def _call(run: dict, name: str, args: dict) -> dict:
    node = UUID(run["active_node_id"]) if run["active_node_id"] else None
    try:
        return await asyncio.wait_for(
            tools.call_tool(name, args, UUID(run["project_id"]), UUID(run["user_id"]), run["model"], node),
            ASK_TIMEOUT if name == "ask_node" else TOOL_TIMEOUT)
    except asyncio.TimeoutError:
        return dict(TIMED_OUT)


async def _run(run: dict, name: str, args: dict) -> dict:
    result = await _call(run, name, args)
    if result == TIMED_OUT and name in ops.READ_ONLY:  # retrying a read is safe; retrying a write is not
        result = await _call(run, name, args)
    return result


async def run_tool(run: dict, iteration: int, index: int, task_key: str | None, name: str, args: dict) -> dict:
    exec_id = await store.begin_execution(run["id"], iteration, index, task_key, name, args)
    result = await _run(run, name, args)
    await store.finish_execution(exec_id, "failed" if "error" in result else "succeeded", result)
    return result


async def resume_in_flight(run: dict) -> None:
    """After a restart: a read that was in flight is simply run again; a write is marked unknown, because nothing
    says whether it happened. The next snapshot tells the model to inspect the tree before retrying it."""
    for row in await store.in_flight(run["id"]):
        if row["name"] in ops.READ_ONLY:
            result = await _run(run, row["name"], row["args"])
            await store.finish_execution(row["id"], "failed" if "error" in result else "succeeded", result)
        else:
            await store.mark_unknown(row["id"])
