from __future__ import annotations

import asyncio
from typing import Any, Callable, Optional

from langgraph.checkpoint.memory import InMemorySaver

from debate.graph import build_graph
from debate.runner import Segment, build_resume, merge_pending, run_segment


def make_config(deps: Any, debate_id: str = "d1") -> dict[str, Any]:
    return {"configurable": {"thread_id": debate_id, "deps": deps}, "recursion_limit": 200}


async def drive(
    deps: Any,
    *,
    rounds: int = 2,
    debate_id: str = "d1",
    answer: Optional[Callable[[list[dict[str, Any]]], dict[str, Any]]] = None,
    on_pause: Optional[Callable[[Segment], Any]] = None,
    max_segments: int = 30,
    graph: Any = None,
    time_left_ms: Optional[Callable[[], int]] = None,
    min_slice_ms: int = 0,
) -> tuple[dict[str, Any], list[Segment], Any]:
    graph = graph or build_graph(InMemorySaver())
    cfg = make_config(deps, debate_id)
    graph_input: Any = {"debate_id": debate_id, "topic": "alpha vs beta", "rounds": rounds}
    segments: list[Segment] = []
    for _ in range(max_segments):
        seg = await run_segment(graph, cfg, graph_input, time_left_ms=time_left_ms, min_slice_ms=min_slice_ms)
        segments.append(seg)
        graph_input = None
        if seg.status == "done":
            break
        if seg.status == "paused":
            if on_pause:
                graph_input = on_pause(seg)
            else:
                merged = merge_pending(seg.interrupts)
                answers = answer(merged) if answer else {m["id"]: "default" for m in merged}
                graph_input = build_resume(seg.interrupts, answers)
    snap = await graph.aget_state(cfg)
    return snap.values, segments, graph


def run(coro: Any) -> Any:
    return asyncio.run(coro)
