from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from langgraph.types import Command


@dataclass
class Segment:
    status: str
    interrupts: list[Any] = field(default_factory=list)
    started_at_ms: int = 0
    ended_at_ms: int = 0

    @property
    def duration_ms(self) -> int:
        return max(0, self.ended_at_ms - self.started_at_ms)


def pending_interrupts(snapshot: Any) -> list[Any]:
    found = list(getattr(snapshot, "interrupts", ()) or ())
    if found:
        return found
    out: list[Any] = []
    for task in getattr(snapshot, "tasks", ()) or ():
        out.extend(getattr(task, "interrupts", ()) or ())
    return out


async def run_segment(
    graph: Any,
    config: dict[str, Any],
    graph_input: Any,
    *,
    time_left_ms: Optional[Callable[[], int]] = None,
    min_slice_ms: int = 0,
) -> Segment:
    started = int(time.time() * 1000)
    seg = await _run(graph, config, graph_input, time_left_ms, min_slice_ms)
    seg.started_at_ms, seg.ended_at_ms = started, int(time.time() * 1000)
    return seg


async def _run(graph: Any, config: dict[str, Any], graph_input: Any, time_left_ms: Any, min_slice_ms: int) -> Segment:
    stream = graph.astream(graph_input, config, stream_mode="values", durability="sync")
    seen = 0
    try:
        async for _ in stream:
            seen += 1
            if seen >= 2 and time_left_ms is not None and time_left_ms() < min_slice_ms:
                break
    finally:
        await stream.aclose()

    snapshot = await graph.aget_state(config)
    interrupts = pending_interrupts(snapshot)
    if interrupts:
        return Segment("paused", interrupts)
    if snapshot.next:
        return Segment("continue")
    return Segment("done")


def merge_pending(interrupts: list[Any]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for it in interrupts:
        who = it.value.get("side") or it.value.get("scope")
        for q in it.value["questions"]:
            m = merged.setdefault(q["id"], {**q, "asked_by": []})
            m["asked_by"].append(who)
    return list(merged.values())


def build_resume(interrupts: list[Any], answers: Optional[dict[str, Any]] = None, skip: bool = False) -> Command:
    resume: dict[str, Any] = {}
    for it in interrupts:
        if skip:
            resume[it.id] = {"skip": True}
        else:
            own = {q["id"] for q in it.value["questions"]}
            resume[it.id] = {"skip": False, "answers": {k: v for k, v in (answers or {}).items() if k in own}}
    return Command(resume=resume)
