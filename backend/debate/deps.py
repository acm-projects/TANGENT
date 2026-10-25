from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Literal, Optional, Protocol

from .schemas import AgentAction, Evidence, FrameResult, JudgeVerdict, OpponentView, QA


@dataclass
class AgentContext:
    side: str
    phase: str
    round: int
    proposition: str
    side_brief: str
    context_text: str
    user_context: list[QA]
    evidence: dict[str, Evidence]
    opponent: Optional[OpponentView]
    steps: list[dict[str, Any]]
    may_search: bool
    may_ask: bool
    force_finish: bool
    searches_left: int = 1
    batch_max: int = 2


@dataclass
class JudgeView:
    rendered: str
    labels: list[str]
    cited_evidence: dict[str, Evidence]
    # Built from the transcript, not from the model: {"A1": {"label": "A", "cited": True}} and
    # {"A": {"total": citation ids used, "unverified": ids not in the evidence pool}}.
    claims: dict[str, dict[str, Any]] = field(default_factory=dict)
    cite_stats: dict[str, dict[str, int]] = field(default_factory=dict)


class Brain(Protocol):
    async def frame(self, topic: str, context: str) -> FrameResult: ...
    # sink (a streaming.StreamSink) is passed only when token streaming is on; a brain may ignore it.
    async def step(self, ctx: AgentContext, sink: Optional[Any] = None) -> AgentAction: ...
    async def judge(self, view: JudgeView, fixed_winner: Optional[str], sink: Optional[Any] = None) -> JudgeVerdict: ...


class Search(Protocol):
    async def search(self, query: str) -> list[Evidence]: ...


@dataclass
class Control:
    id: str
    action: Literal["pick_side", "stop"]
    side: Optional[str] = None


class ControlStore(Protocol):
    async def pending(self, debate_id: str, applied_id: Optional[str] = None) -> Optional[Control]: ...


class Emitter(Protocol):
    async def emit(self, type: str, payload: dict[str, Any], key: Optional[str] = None) -> bool: ...


class ResultWriter(Protocol):
    async def create_result(self, debate_id: str, payload: dict[str, Any]) -> str: ...


@dataclass
class Deps:
    brain: Brain
    search: Search
    control: ControlStore
    emitter: Emitter
    context_loader: Callable[[str], Awaitable[tuple[str, list[str]]]]
    writer: ResultWriter
    rng: random.Random = field(default_factory=random.Random)
    max_agent_steps: int = 10_000
    max_cost_usd: Optional[float] = None
    stream_tokens: bool = False  # emit `token` events while a debater or the judge writes
    stream_interval_s: float = 0.25
    ask_cap: int = 2
    search_cap: int = 4
    search_batch_max: int = 2  # queries per search call, so one search is always left to follow up on what came back
    turn_step_cap: int = 12  # counts thoughts and search results: 4 searches in 2 batches use 6, plus up to 2 asks