from __future__ import annotations

import hashlib
from typing import Any, Literal, Optional, Union

from pydantic import BaseModel, Field

Side = Literal["for", "against"]
Phase = Literal["research", "opening", "rebuttal", "closing"]
EndReason = Literal[
    "rounds_exhausted",
    "budget_exhausted",
    "user_picked",
    "user_stopped",
]


def question_id(prompt: str) -> str:
    return hashlib.sha1(" ".join(prompt.lower().split()).encode()).hexdigest()[:8]


class Usage(BaseModel):
    model: str = ""
    role: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    reasoning_tokens: int = 0
    cached_tokens: int = 0
    cost: float = 0.0
    latency_ms: int = 0
    generation_id: str = ""
    attempts: int = 1  # API calls behind this record: more than 1 means the reply was retried


class Claim(BaseModel):
    id: str
    text: str
    evidence_ids: list[str] = Field(default_factory=list)


class TurnOutput(BaseModel):
    thinking: list[str] = Field(default_factory=list)
    argument: str
    claims: list[Claim] = Field(default_factory=list)


class Turn(TurnOutput):
    side: Side
    phase: Phase
    round: int = 0
    truncated: bool = False


class Question(BaseModel):
    id: str = ""
    prompt: str
    type: Literal["single", "multi"] = "single"
    options: list[dict[str, Any]] = Field(default_factory=list)
    allow_other: bool = True

    def model_post_init(self, __context: Any) -> None:
        if not self.id:
            self.id = question_id(self.prompt)


class QA(BaseModel):
    id: str
    prompt: str
    answer: Union[str, list[str], None] = None
    asked_by: Optional[str] = None


class Evidence(BaseModel):
    id: str
    title: str
    year: Optional[int] = None
    url: str = ""
    snippet: str = ""


class OpponentView(BaseModel):
    argument: str
    claims: list[Claim]


class SearchAction(BaseModel):
    kind: Literal["search"] = "search"
    query: str
    more_queries: list[str] = Field(default_factory=list)  # extra searches run together with `query` in one step
    thinking: str = ""
    usage: Optional[Usage] = None


class AskAction(BaseModel):
    kind: Literal["ask"] = "ask"
    questions: list[Question]
    thinking: str = ""
    usage: Optional[Usage] = None


class FinishAction(BaseModel):
    kind: Literal["finish"] = "finish"
    turn: TurnOutput
    usage: Optional[Usage] = None


AgentAction = Union[SearchAction, AskAction, FinishAction]


class FrameResult(BaseModel):
    proposition: str
    side_briefs: dict[str, str]
    questions: list[Question] = Field(default_factory=list)
    checks: Optional[dict[str, bool]] = None  # criterion_stated, setting_stated, context_resolves; code decides whether to ask
    usage: Optional[Usage] = None


class JudgeVerdict(BaseModel):
    winner: Literal["A", "B", "none"]
    would_have_chosen: Literal["A", "B", "none"]
    confidence: float
    rationale: str
    summary: str
    final_output: str
    scores: dict[str, Any] = Field(default_factory=dict)
    strongest_counterpoints: list[str] = Field(default_factory=list)
    verdict_flips_if: list[str] = Field(default_factory=list)
    rubric: Optional[dict[str, Any]] = None  # claim labels + criteria scores; when present, code computes winner and confidence
    usage: Optional[Usage] = None