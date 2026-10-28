from __future__ import annotations

import operator
from typing import Annotated, Any, Optional, TypedDict


def merge_dict(a: Optional[dict], b: Optional[dict]) -> dict:
    return {**(a or {}), **(b or {})}


def sum_dict(a: Optional[dict], b: Optional[dict]) -> dict:
    out = dict(a or {})
    for k, v in (b or {}).items():
        out[k] = out.get(k, 0) + v
    return out


def merge_by_id(a: Optional[list], b: Optional[list]) -> list:
    out = list(a or [])
    seen = {x["id"] for x in out}
    for x in b or []:
        if x["id"] not in seen:
            out.append(x)
            seen.add(x["id"])
    return out


class DebateState(TypedDict, total=False):
    debate_id: str
    topic: str
    rounds: int
    context_text: str
    proposition: str
    side_briefs: dict[str, str]
    pending_frame_questions: list[dict[str, Any]]
    user_context: Annotated[list[dict[str, Any]], merge_by_id]
    evidence_pool: Annotated[dict[str, Any], merge_dict]
    turns: Annotated[list[dict[str, Any]], operator.add]
    asks_used: Annotated[dict[str, int], sum_dict]
    metrics: Annotated[list[dict[str, Any]], operator.add]
    usage: Annotated[list[dict[str, Any]], operator.add]
    phase: Optional[str]
    round: int
    dispatch: list[dict[str, Any]]
    end_reason: Optional[str]
    picked_side: Optional[str]
    applied_control_id: Optional[str]
    citation_report: dict[str, list[str]]
    ab_map: dict[str, str]
    verdict: dict[str, Any]
    result_node_id: str


class DebaterState(TypedDict, total=False):
    in_debate_id: str
    in_side: str
    in_phase: str
    in_round: int
    in_proposition: str
    in_brief: str
    in_context: str
    in_evidence: dict[str, Any]
    in_user_context: list[dict[str, Any]]
    in_opponent: Optional[dict[str, Any]]
    in_asks_remaining: int
    in_may_search: bool
    in_may_ask: bool
    in_applied_control: Optional[str]

    steps: list[dict[str, Any]]
    searches: int
    pending_more: list
    pending_search: Optional[str]
    pending_ask: Optional[list[dict[str, Any]]]
    action_kind: str
    finish: Optional[dict[str, Any]]
    forced: bool

    turns: Annotated[list[dict[str, Any]], operator.add]
    evidence_pool: Annotated[dict[str, Any], merge_dict]
    user_context: Annotated[list[dict[str, Any]], merge_by_id]
    asks_used: Annotated[dict[str, int], sum_dict]
    metrics: Annotated[list[dict[str, Any]], operator.add]
    usage: Annotated[list[dict[str, Any]], operator.add]
