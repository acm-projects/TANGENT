from __future__ import annotations

import hashlib
import random
from typing import Any, Callable, Optional

from .deps import AgentContext, Control, Deps, JudgeView
from .schemas import (
    AgentAction,
    Claim,
    Evidence,
    FinishAction,
    FrameResult,
    JudgeVerdict,
    SearchAction,
    TurnOutput,
    Usage,
)


def tok(text: str) -> str:
    return hashlib.sha1(text.encode()).hexdigest()[:4]


class InMemoryControl:
    def __init__(self) -> None:
        self._latest: dict[str, Control] = {}
        self._n = 0

    def request(self, debate_id: str, action: str, side: Optional[str] = None) -> Control:
        self._n += 1
        c = Control(id=f"c{self._n}", action=action, side=side)  # type: ignore[arg-type]
        self._latest[debate_id] = c
        return c

    async def pending(self, debate_id: str, applied_id: Optional[str] = None) -> Optional[Control]:
        c = self._latest.get(debate_id)
        return c if c and c.id != applied_id else None


class InMemoryEmitter:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []
        self._keys: set[str] = set()

    async def emit(self, type: str, payload: dict[str, Any], key: Optional[str] = None) -> bool:
        if key is not None:
            if key in self._keys:
                return False
            self._keys.add(key)
        self.events.append({"type": type, **payload})
        return True

    def of(self, type: str) -> list[dict[str, Any]]:
        return [e for e in self.events if e["type"] == type]


class InMemoryWriter:
    def __init__(self) -> None:
        self.results: dict[str, dict[str, Any]] = {}
        self.calls = 0

    async def create_result(self, debate_id: str, payload: dict[str, Any]) -> str:
        self.calls += 1
        if debate_id not in self.results:
            self.results[debate_id] = payload
        return f"node-{debate_id}"


class FakeSearch:
    def __init__(self) -> None:
        self.queries: list[str] = []

    async def search(self, query: str) -> list[Evidence]:
        self.queries.append(query)
        eid = f"ev-{tok(query)}"
        return [Evidence(id=eid, title=f"Paper {eid}", year=2024, url=f"https://x/{eid}", snippet=f"snippet on {query}")]


class ScriptedBrain:
    def __init__(
        self,
        script: Optional[dict[tuple, Any]] = None,
        frame_questions: Optional[list] = None,
        usage: Optional[Usage] = None,
    ) -> None:
        self.usage = usage
        self.script = script or {}
        self.frame_questions = frame_questions or []
        self.branches: Optional[list] = None  # None disables branch proposals; else a list of Branch
        self.branch_calls: list[dict[str, Any]] = []
        self.conclusion: Optional[str] = None  # None disables the check; else "supported"|"not_supported"|"neither"
        self.conclusion_calls: list[tuple[str, str]] = []
        self.contexts: list[AgentContext] = []
        self.judge_views: list[JudgeView] = []
        self.fixed_winners: list[Optional[str]] = []
        self.on_step: Optional[Callable[[AgentContext], None]] = None

    def _u(self, result: Any) -> Any:
        if self.usage is not None and getattr(result, "usage", None) is None:
            return result.model_copy(update={"usage": self.usage})
        return result

    async def frame(self, topic: str, context: str) -> FrameResult:
        return self._u(FrameResult(
            proposition="Choose alpha over beta",
            side_briefs={"for": "argue alpha", "against": "argue beta"},
            questions=self.frame_questions,
        ))

    async def _stream_text(self, sink: Any, text: str) -> None:
        if sink is None or not text:
            return
        await sink.start()
        mid = max(1, len(text) // 2)
        await sink.push(text[:mid])
        await sink.push(text[mid:])

    async def step(self, ctx: AgentContext, sink: Any = None) -> AgentAction:
        action = await self._step(ctx)
        if getattr(action, "kind", "") == "finish":
            await self._stream_text(sink, action.turn.argument)
        return action

    async def _step(self, ctx: AgentContext) -> AgentAction:
        self.contexts.append(ctx)
        if self.on_step:
            self.on_step(ctx)
        n = len(ctx.steps)
        scripted = self.script.get((ctx.side, ctx.phase, ctx.round, n))
        if scripted is not None:
            return self._u(scripted(ctx) if callable(scripted) else scripted)
        if ctx.force_finish:
            return self._u(self._finish(ctx, thinking=["finishing early on request"]))
        if ctx.phase == "research" and n == 0 and ctx.may_search:
            return self._u(SearchAction(query=f"{tok(ctx.side)} evidence", thinking="looking for supporting papers"))
        return self._u(self._finish(ctx))

    def _finish(self, ctx: AgentContext, thinking: Optional[list[str]] = None) -> FinishAction:
        me = tok(ctx.side)
        thoughts = thinking or []
        if ctx.opponent and not thinking:
            thoughts = [f"opponent claim {c.id} rests on weak evidence" for c in ctx.opponent.claims]
        ev = [next(iter(ctx.evidence))] if ctx.evidence else []
        cid = f"{ctx.side}-{ctx.phase}-{ctx.round}-1"
        return FinishAction(
            turn=TurnOutput(
                thinking=thoughts or ["reasoning about the proposition"],
                argument=f"argument {me} {ctx.phase} {ctx.round}",
                claims=[Claim(id=cid, text=f"claim {me} {ctx.phase} {ctx.round}", evidence_ids=ev)],
            )
        )

    async def propose_branches(self, proposition, summary, open_questions, flips, counterpoints, max_branches=5):
        self.branch_calls.append({"proposition": proposition, "summary": summary, "open_questions": open_questions,
                                  "flips": list(flips), "counterpoints": list(counterpoints)})
        if self.branches is None:
            raise AttributeError("no scripted branches")  # same effect as a brain without the method
        return list(self.branches)[:max_branches], self.usage

    async def check_conclusion(self, proposition: str, text: str) -> tuple[str, Optional[Usage]]:
        self.conclusion_calls.append((proposition, text))
        if self.conclusion is None:
            raise AttributeError("no scripted conclusion")  # same effect as a brain without the method
        return self.conclusion, self.usage

    async def judge(self, view: JudgeView, fixed_winner: Optional[str], sink: Any = None) -> JudgeVerdict:
        await self._stream_text(sink, "final output text")
        self.judge_views.append(view)
        self.fixed_winners.append(fixed_winner)
        return self._u(JudgeVerdict(
            winner=fixed_winner or "A",
            would_have_chosen="A",
            confidence=0.7,
            rationale="rationale text",
            summary="summary text",
            final_output="final output text",
            scores={"A": 8, "B": 6},
            strongest_counterpoints=["counterpoint one"],
            verdict_flips_if=["budget changes"],
        ))


def make_deps(
    brain: Optional[ScriptedBrain] = None,
    *,
    context_text: str = "earlier chat about alpha and beta",
    seed: int = 1,
    **overrides: Any,
) -> Deps:
    async def loader(debate_id: str) -> tuple[str, list[str]]:
        return context_text, ["n1", "n2"]

    return Deps(
        brain=brain or ScriptedBrain(),
        search=FakeSearch(),
        control=InMemoryControl(),
        emitter=InMemoryEmitter(),
        context_loader=loader,
        writer=InMemoryWriter(),
        rng=random.Random(seed),
        **overrides,
    )
