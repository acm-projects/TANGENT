"""The bounded, iterative agent loop: observe (snapshot) -> decide (one LLM call) -> act (one op, one write, or a batch
of reads) -> evaluate next step. The model makes every research decision; this module only enforces the rules."""

import asyncio
import json
import logging
import time

from app.agent import executor, ops, prompts, store
from app.agent.ops import OpError, State
from app.core.openrouter import stream_openrouter
from app.papers import service as paper_service

log = logging.getLogger(__name__)

LLM_ATTEMPTS = 3
WRAP_UP_NOTE = "\n\nYOU ARE OUT OF BUDGET ({why}). Call finish_research now with your honest assessment of the goal."


class LLMError(Exception):
    pass


async def decide(run: dict, st: State, iteration: int, tool_list: list, tool_choice: str | None = None,
                 note: str = "") -> tuple[str, list[dict]]:
    """One model call. Retries provider failures; every attempt is logged with its duration and usage."""
    messages = [{"role": "system", "content": prompts.system_prompt()},
                {"role": "user", "content": prompts.snapshot(st) + note}]
    error = ""
    for attempt in range(1, LLM_ATTEMPTS + 1):
        started, text, calls, usage, error = time.monotonic(), "", [], None, ""
        try:
            async for ev in stream_openrouter(messages, run["model"], tools=tool_list, tool_choice=tool_choice):
                if "error" in ev:
                    error = str(ev["error"])[:500]
                    break
                text += ev.get("text", "")
                calls = ev.get("tool_calls", calls)
                usage = ev.get("usage", usage)
        except Exception as exc:  # network failures are retried like provider errors
            error = f"{type(exc).__name__}: {exc}"[:500]
        if not error and not calls and paper_service.LEAK_MARKER in text:  # some models write the call as text
            calls = paper_service.parse_leaked_tool_calls(text)
            text = text.split(paper_service.LEAK_MARKER)[0]
        await store.log_llm_call(run["id"], iteration, attempt, run["model"], messages,
                                 None if error else {"text": text, "tool_calls": calls}, usage, error or None,
                                 int((time.monotonic() - started) * 1000))
        if not error:
            return text.strip(), calls
        await asyncio.sleep(2 * attempt)
    raise LLMError(f"The model failed after {LLM_ATTEMPTS} attempts: {error}")


def _args(call: dict):
    try:
        args = json.loads(call["function"]["arguments"] or "{}")
    except ValueError:
        return None
    return args if isinstance(args, dict) else None


async def _reject(run_id: str, iteration: int, name: str, args, error: str) -> None:
    streak = await store.reject(run_id, iteration, 0, name, args, error)
    if streak >= ops.MAX_INVALID_STREAK:
        await store.fail_run(run_id, f"{streak} invalid steps in a row; last: {error}")


async def step(run_id: str, st: State, iteration: int) -> None:
    run = st.run
    text, calls = await decide(run, st, iteration, ops.ALL_TOOLS)
    names = [c["function"]["name"] for c in calls]
    if error := ops.batch_error(names):
        return await _reject(run_id, iteration, names[0] if names else "(no tool call)", text[:300], error)
    parsed = [_args(c) for c in calls]
    if any(a is None for a in parsed):
        return await _reject(run_id, iteration, names[0], "unparseable", "The tool arguments were not a valid JSON object.")

    if names[0] in ops.OPS:
        try:
            a = ops.check(st, names[0], parsed[0])
        except OpError as exc:
            return await _reject(run_id, iteration, names[0], parsed[0], str(exc))
        await store.apply_op(run_id, st, iteration, 0, names[0], a)
        return

    if run["tool_calls"] + len(calls) > ops.MAX_TOOL_CALLS:
        return await _reject(run_id, iteration, names[0], parsed[0],
                             f"Only {ops.MAX_TOOL_CALLS - run['tool_calls']} tool calls are left in the budget.")
    task_key = store.active_task(st)
    if names[0] == "delete_node" and str(parsed[0].get("node_id")) not in run["authorized_deletes"]:
        return await store.request_delete_confirmation(run_id, iteration, 0, str(parsed[0].get("node_id")), task_key)
    await asyncio.gather(*(executor.run_tool(run, iteration, i, task_key, n, a)
                           for i, (n, a) in enumerate(zip(names, parsed))))


async def wrap_up(run_id: str, why: str) -> None:
    """A limit was hit: close open tasks, give the model one chance to assess the goal, else record an honest fallback."""
    await store.skip_open_tasks(run_id, f"run limit reached: {why}")
    st = await store.load_state(run_id)
    try:
        iteration = await store.begin_iteration(run_id)
        if iteration is None:
            return
        _, calls = await decide(st.run, st, iteration, ops.FINISH_ONLY, "required", WRAP_UP_NOTE.format(why=why))
        call = next((c for c in calls if c["function"]["name"] == "finish_research"), None)
        args = _args(call) if call else None
        if args is not None:
            await store.apply_op(run_id, st, iteration, 0, "finish_research", ops.check(st, "finish_research", args))
            return
    except store.Stopped:
        return
    except (OpError, LLMError) as exc:
        log.warning("agent run %s: wrap-up failed: %s", run_id, exc)
    try:
        await store.stop_with_limits(run_id, st, why)
    except store.Stopped:
        pass


async def run_loop(run_id: str) -> None:
    await executor.resume_in_flight((await store.load_state(run_id)).run)
    while True:
        st = await store.load_state(run_id)
        if st.run["status"] != "running":  # waiting for the user, finished, failed or cancelled
            return
        if why := ops.limit_reached(st.run):
            return await wrap_up(run_id, why)
        iteration = await store.begin_iteration(run_id)
        if iteration is None:
            return
        try:
            await step(run_id, st, iteration)
        except store.Stopped:  # cancelled mid-step: drop it
            return
