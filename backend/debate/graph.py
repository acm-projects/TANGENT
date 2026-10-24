from __future__ import annotations

import asyncio
import time
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send, interrupt

from .deps import AgentContext, Deps
from .judge_view import build_judge_view
from .framing import choose_questions
from .scoring import score_rubric
from .streaming import make_sink, turn_id
from .metrics import summarize_timings, summarize_usage, total_cost, usage_record
from .schemas import (
    QA,
    Evidence,
    FinishAction,
    OpponentView,
    Question,
    Turn,
    TurnOutput,
)
from .state import DebaterState, DebateState

BOTH = ["for", "against"]
ANSWERABLE_PHASES = ("research", "opening", "rebuttal")


def _deps(config: RunnableConfig) -> Deps:
    return config["configurable"]["deps"]


def _did(config: RunnableConfig) -> str:
    return config["configurable"]["thread_id"]


def _other(side: str) -> str:
    return "against" if side == "for" else "for"


def _metric(node: str, side: Any, phase: Any, rnd: Any, t0: float, **extra: Any) -> dict[str, Any]:
    duration_ms = int((time.monotonic() - t0) * 1000)
    return {
        "node": node,
        "side": side,
        "phase": phase,
        "round": rnd,
        "started_at_ms": int(time.time() * 1000) - duration_ms,
        "duration_ms": duration_ms,
        **extra,
    }


def deanonymize(text: str, ab: dict[str, str]) -> str:
    for label, side in ab.items():
        text = text.replace(f"Position {label}", f"the {side.upper()} side")
    return text


def _qa_from_reply(questions: list[Question], reply: Any, asked_by: str) -> list[dict[str, Any]]:
    if not isinstance(reply, dict) or reply.get("skip"):
        return []
    answers = reply.get("answers", {})
    return [
        QA(id=q.id, prompt=q.prompt, answer=answers[q.id], asked_by=asked_by).model_dump()
        for q in questions
        if q.id in answers
    ]


async def agent_node(state: DebaterState, config: RunnableConfig) -> dict[str, Any]:
    d = _deps(config)
    t0 = time.monotonic()
    did, side = state["in_debate_id"], state["in_side"]
    phase, rnd = state["in_phase"], state["in_round"]
    steps = list(state.get("steps", []))

    ctl = await d.control.pending(did, state.get("in_applied_control"))
    forced = ctl is not None or len(steps) >= d.turn_step_cap

    known_ctx = list(state.get("in_user_context", [])) + list(state.get("user_context", []))
    known_ev = {**state.get("in_evidence", {}), **state.get("evidence_pool", {})}
    asks_left = state.get("in_asks_remaining", 0) - state.get("asks_used", {}).get(side, 0)
    opp = state.get("in_opponent")

    ctx = AgentContext(
        side=side,
        phase=phase,
        round=rnd,
        proposition=state["in_proposition"],
        side_brief=state["in_brief"],
        context_text=state["in_context"],
        user_context=[QA(**x) for x in known_ctx],
        evidence={k: Evidence(**v) for k, v in known_ev.items()},
        opponent=OpponentView(**opp) if opp else None,
        steps=steps,
        may_search=state.get("in_may_search", False) and state.get("searches", 0) < d.search_cap,
        searches_left=max(0, d.search_cap - state.get("searches", 0)),
        batch_max=d.search_batch_max,
        may_ask=state.get("in_may_ask", False) and asks_left > 0,
        force_finish=forced,
    )
    sink = make_sink(d, did, side, phase, rnd)
    try:
        action = await (d.brain.step(ctx, sink) if sink is not None else d.brain.step(ctx))
    finally:
        if sink is not None:
            await sink.close()
    usage = usage_record(action.usage, role=side, phase=phase, round=rnd)

    if action.kind != "finish" and forced:
        action = FinishAction(
            turn=TurnOutput(argument="(turn cut short)", thinking=["turn cut short before finishing"])
        )
    metric = _metric("agent", side, phase, rnd, t0, step=len(steps))
    key = f"{did}:{side}:{phase}:{rnd}:{len(steps)}"

    if action.kind == "search" and not ctx.may_search:
        return {
            "steps": steps + [{"type": "rejected", "what": "search"}],
            "action_kind": "again",
            "metrics": [metric],
            "usage": usage,
        }
    if action.kind == "ask" and not ctx.may_ask:
        return {
            "steps": steps + [{"type": "rejected", "what": "ask"}],
            "action_kind": "again",
            "metrics": [metric],
            "usage": usage,
        }

    if action.kind == "search":
        await d.emitter.emit("thinking", {"side": side, "phase": phase, "round": rnd, "text": action.thinking}, key=f"think:{key}")
        queries = [action.query] + [q for q in action.more_queries if q and q != action.query]
        queries = queries[: max(1, min(ctx.searches_left, d.search_batch_max))]
        for i, q in enumerate(queries):
            await d.emitter.emit("tool_called", {"side": side, "tool": "search_papers", "query": q},
                                 key=f"tool:{key}" if i == 0 else f"tool:{key}:{i}")
        return {
            "pending_search": queries[0],
            "pending_more": queries[1:],
            "steps": steps + [{"type": "thought", "text": action.thinking}],
            "action_kind": "search",
            "metrics": [metric],
            "usage": usage,
        }
    if action.kind == "ask":
        await d.emitter.emit("thinking", {"side": side, "phase": phase, "round": rnd, "text": action.thinking}, key=f"think:{key}")
        return {
            "pending_ask": [q.model_dump() for q in action.questions[:3]],
            "steps": steps + [{"type": "thought", "text": action.thinking}],
            "action_kind": "ask",
            "metrics": [metric],
            "usage": usage,
        }
    return {
        "finish": action.turn.model_dump(),
        "forced": forced,
        "action_kind": "finish",
        "metrics": [metric],
        "usage": usage,
    }


async def search_node(state: DebaterState, config: RunnableConfig) -> dict[str, Any]:
    d = _deps(config)
    t0 = time.monotonic()
    queries = [state["pending_search"]] + list(state.get("pending_more") or [])

    async def one(q: str):
        try:
            return await d.search.search(q), None
        except Exception as exc:  # a failed lookup must not kill the debate; the agent is told and carries on
            return [], f"{type(exc).__name__}"

    outcomes = await asyncio.gather(*(one(q) for q in queries))
    pool: dict[str, Any] = {}
    observations = []
    for q, (results, error) in zip(queries, outcomes):
        pool.update({e.id: e.model_dump() for e in results})
        observations.append({
            "type": "search",
            "query": q,
            "results": [{"id": e.id, "title": e.title, "snippet": e.snippet[:200]} for e in results],
            **({"error": f"search unavailable ({error}); continue without new sources"} if error else {}),
        })
    return {
        "evidence_pool": pool,
        "steps": list(state.get("steps", [])) + observations,
        "searches": state.get("searches", 0) + len(queries),
        "pending_search": None,
        "pending_more": [],
        "metrics": [_metric("search", state["in_side"], state["in_phase"], state["in_round"], t0)],
    }


async def ask_user_node(state: DebaterState, config: RunnableConfig) -> dict[str, Any]:
    side = state["in_side"]
    questions = [Question(**q) for q in state["pending_ask"]]
    reply = interrupt(
        {
            "scope": "debater",
            "side": side,
            "phase": state["in_phase"],
            "round": state["in_round"],
            "questions": [q.model_dump() for q in questions],
        }
    )
    qa = _qa_from_reply(questions, reply, asked_by=side)
    skipped = not qa
    return {
        "user_context": qa,
        "asks_used": {side: 1},
        "pending_ask": None,
        "steps": list(state.get("steps", [])) + [{"type": "answer", "skipped": skipped, "count": len(qa)}],
    }


async def emit_node(state: DebaterState, config: RunnableConfig) -> dict[str, Any]:
    d = _deps(config)
    t0 = time.monotonic()
    did, side = state["in_debate_id"], state["in_side"]
    phase, rnd = state["in_phase"], state["in_round"]
    out = TurnOutput(**state["finish"])

    turn = Turn(
        **out.model_dump(),
        side=side,
        phase=phase,
        round=rnd,
        truncated=bool(state.get("forced")),
    )
    await d.emitter.emit(
        "turn_completed",
        {
            "turn_id": turn_id(did, side, phase, rnd),
            "side": side,
            "phase": phase,
            "round": rnd,
            "thinking": turn.thinking,
            "argument": turn.argument,
            "truncated": turn.truncated,
        },
        key=f"turn:{did}:{side}:{phase}:{rnd}",
    )
    return {"turns": [turn.model_dump()], "metrics": [_metric("emit", side, phase, rnd, t0)]}


def route_agent(state: DebaterState) -> str:
    return {"search": "search", "ask": "ask_user", "finish": "emit", "again": "agent"}[state["action_kind"]]


def build_debater() -> Any:
    g = StateGraph(DebaterState)
    g.add_node("agent", agent_node)
    g.add_node("search", search_node)
    g.add_node("ask_user", ask_user_node)
    g.add_node("emit", emit_node)
    g.add_edge(START, "agent")
    g.add_conditional_edges("agent", route_agent, ["search", "ask_user", "emit", "agent"])
    g.add_edge("search", "agent")
    g.add_edge("ask_user", "agent")
    g.add_edge("emit", END)
    return g.compile()


async def intake(state: DebateState, config: RunnableConfig) -> dict[str, Any]:
    d = _deps(config)
    t0 = time.monotonic()
    text, node_ids = await d.context_loader(_did(config))
    await d.emitter.emit(
        "phase_changed",
        {"phase": "intake", "context_nodes": len(node_ids)},
        key=f"phase:{_did(config)}:intake",
    )
    return {"context_text": text, "metrics": [_metric("intake", None, "intake", 0, t0, context_nodes=len(node_ids))]}


async def frame(state: DebateState, config: RunnableConfig) -> dict[str, Any]:
    d = _deps(config)
    t0 = time.monotonic()
    r = await d.brain.frame(state["topic"], state.get("context_text", ""))
    questions = choose_questions(state["topic"], r.checks, r.questions)
    return {
        "proposition": r.proposition,
        "side_briefs": r.side_briefs,
        "pending_frame_questions": [q.model_dump() for q in questions],
        "metrics": [_metric("frame", None, "frame", 0, t0)],
        "usage": usage_record(r.usage, role="frame", phase="frame", round=0),
    }


def route_after_frame(state: DebateState) -> str:
    return "ask_frame" if state.get("pending_frame_questions") else "advance"


async def ask_frame(state: DebateState, config: RunnableConfig) -> dict[str, Any]:
    questions = [Question(**q) for q in state["pending_frame_questions"]]
    reply = interrupt({"scope": "frame", "questions": [q.model_dump() for q in questions]})
    return {
        "user_context": _qa_from_reply(questions, reply, asked_by="frame"),
        "pending_frame_questions": [],
    }


async def reframe(state: DebateState, config: RunnableConfig) -> dict[str, Any]:
    """The proposition and side briefs were written before the user answered. Redo them with the answers in hand."""
    qa = [q for q in state.get("user_context", []) if q.get("asked_by") == "frame" and q.get("answer") is not None]
    if not qa:
        return {}
    d = _deps(config)
    t0 = time.monotonic()
    lines = [f"- {q['prompt']} -> {q['answer']}" for q in qa]
    topic = state["topic"] + "\n\nUser clarifications (the user already answered these; the proposition must reflect them):\n" + "\n".join(lines)
    r = await d.brain.frame(topic, state.get("context_text", ""))
    return {
        "proposition": r.proposition,
        "side_briefs": r.side_briefs,
        "metrics": [_metric("reframe", None, "reframe", 0, t0)],
        "usage": usage_record(r.usage, role="frame", phase="reframe", round=0),
    }


def decide(phase, rnd, rounds, end_reason, picked):
    if phase == "closing" or end_reason in ("user_stopped", "budget_exhausted"):
        return "done", [], rnd, end_reason
    if end_reason == "user_picked":
        return "closing", [picked], rnd, end_reason
    if phase is None:
        return "research", BOTH, 0, end_reason
    if phase == "research":
        return "opening", BOTH, 0, end_reason
    if phase == "opening":
        return "rebuttal", BOTH, 1, end_reason
    if rnd < rounds:
        return "rebuttal", BOTH, rnd + 1, end_reason
    return "closing", BOTH, rnd, "rounds_exhausted"


async def advance(state: DebateState, config: RunnableConfig) -> dict[str, Any]:
    d = _deps(config)
    t0 = time.monotonic()
    did = _did(config)
    phase, rnd = state.get("phase"), state.get("round", 0)
    end_reason, picked = state.get("end_reason"), state.get("picked_side")
    upd: dict[str, Any] = {}

    ctl = await d.control.pending(did, state.get("applied_control_id"))
    if ctl:
        upd["applied_control_id"] = ctl.id
        if ctl.action == "pick_side":
            end_reason, picked = "user_picked", ctl.side
        else:
            end_reason, picked = "user_stopped", None
        await d.emitter.emit("control_applied", {"action": ctl.action, "side": ctl.side}, key=f"control:{did}:{ctl.id}")
    elif end_reason is None:
        agent_steps = sum(1 for m in state.get("metrics", []) if m["node"] == "agent")
        over_cost = d.max_cost_usd is not None and total_cost(state.get("usage", [])) >= d.max_cost_usd
        if agent_steps >= d.max_agent_steps or over_cost:
            end_reason = "budget_exhausted"

    nxt, sides, nrnd, end_reason = decide(phase, rnd, state.get("rounds", 2), end_reason, picked)

    dispatch = []
    for side in sides:
        opp = _other(side)
        opponent_view = None
        if nxt in ("rebuttal", "closing"):
            prior = [t for t in state.get("turns", []) if t["side"] == opp and t["phase"] != "research"]
            if prior:
                last = prior[-1]
                opponent_view = OpponentView(argument=last["argument"], claims=last["claims"]).model_dump()
        dispatch.append(
            {
                "in_side": side,
                "in_phase": nxt,
                "in_round": nrnd,
                "in_opponent": opponent_view,
                "in_asks_remaining": d.ask_cap - state.get("asks_used", {}).get(side, 0),
                "in_may_search": nxt in ("research", "rebuttal"),
                "in_may_ask": nxt in ANSWERABLE_PHASES,
                "in_applied_control": upd.get("applied_control_id", state.get("applied_control_id")),
            }
        )

    await d.emitter.emit(
        "phase_changed",
        {"phase": nxt, "round": nrnd, "sides": sides, "end_reason": end_reason},
        key=f"phase:{did}:{nxt}:{nrnd}",
    )
    upd.update(
        phase=nxt,
        round=nrnd,
        dispatch=dispatch,
        end_reason=end_reason,
        picked_side=picked,
        metrics=[_metric("advance", None, nxt, nrnd, t0)],
    )
    return upd


def route_advance(state: DebateState) -> Any:
    if state["phase"] == "done":
        return "verify"
    return [
        Send(
            "debater",
            {
                **meta,
                "in_debate_id": state["debate_id"],
                "in_proposition": state["proposition"],
                "in_brief": state["side_briefs"][meta["in_side"]],
                "in_context": state.get("context_text", ""),
                "in_evidence": state.get("evidence_pool", {}),
                "in_user_context": state.get("user_context", []),
            },
        )
        for meta in state["dispatch"]
    ]


async def verify(state: DebateState, config: RunnableConfig) -> dict[str, Any]:
    t0 = time.monotonic()
    pool = state.get("evidence_pool", {})
    report: dict[str, list[str]] = {"for": [], "against": []}
    for t in state.get("turns", []):
        if t["phase"] == "research":
            continue
        for c in t["claims"]:
            report[t["side"]] += [e for e in c["evidence_ids"] if e not in pool]
    return {"citation_report": report, "metrics": [_metric("verify", None, "verify", 0, t0)]}


async def judge(state: DebateState, config: RunnableConfig) -> dict[str, Any]:
    d = _deps(config)
    t0 = time.monotonic()
    ab = {"A": "for", "B": "against"} if d.rng.random() < 0.5 else {"A": "against", "B": "for"}
    label_of = {side: label for label, side in ab.items()}
    view = build_judge_view(dict(state), label_of)
    fixed = label_of[state["picked_side"]] if state.get("end_reason") == "user_picked" else None
    if not any(t["phase"] != "research" for t in state.get("turns", [])):
        # stopped before anyone argued: nothing to judge, and no model call to pay for
        verdict = {
            "winner_side": "no_clear_winner", "would_have_chosen_side": "no_clear_winner", "confidence": 0.0,
            "rationale": "The debate was ended before either side made an argument.",
            "summary": "The debate was ended before either side made an argument, so there is no verdict.",
            "final_output": "No arguments were made, so there is no conclusion to report. Start the debate again to get one.",
            "scores": {}, "strongest_counterpoints": [], "verdict_flips_if": [],
        }
        return {"ab_map": ab, "verdict": verdict, "metrics": [_metric("judge", None, "judge", 0, t0)]}
    sink = make_sink(d, _did(config), "judge", "judging", 0)
    try:
        v = await (d.brain.judge(view, fixed, sink) if sink is not None else d.brain.judge(view, fixed))
    finally:
        if sink is not None:
            await sink.close()

    calc = None
    if v.rubric:
        # The model labelled claims and scored criteria; the winner, scores and confidence are arithmetic on those.
        calc = score_rubric(v.rubric, view.claims, view.cite_stats, fixed)
        v = v.model_copy(update={
            "winner": calc["winner"], "would_have_chosen": calc["would_have_chosen"],
            "confidence": calc["confidence"], "scores": dict(calc["totals"]),
        })
        if not calc["text_matches_scores"] and not fixed:
            v = v.model_copy(update={"final_output": (
                "> Scoring note: the rubric totals give a different result than the text below was written for. "
                "The winner shown follows the rubric.\n\n" + v.final_output)})

    to_side = {"A": ab["A"], "B": ab["B"], "none": "no_clear_winner"}
    verdict = v.model_dump()
    for k in ("rationale", "summary", "final_output"):
        verdict[k] = deanonymize(verdict[k], ab)
    for k in ("strongest_counterpoints", "verdict_flips_if"):
        verdict[k] = [deanonymize(x, ab) for x in verdict[k]]
    verdict["scores"] = {ab[k]: x for k, x in verdict["scores"].items() if k in ab}
    if calc:
        verdict["scores"]["rubric"] = {
            "totals": {ab[k]: x for k, x in calc["totals"].items()},
            "criteria": {ab[k]: x for k, x in calc["criteria"].items()},
            "claim_counts": {ab[k]: x for k, x in calc["claim_counts"].items()},
            "notes": {ab[str(c.get("position", "")).upper()]: deanonymize(str(c.get("note", "")), ab) for c in v.rubric["criteria"] if str(c.get("position", "")).upper() in ab},
            "weights": calc["weights"], "margin": calc["margin"], "gap": calc["gap"], "coverage": calc["coverage"],
            "verified_share": calc["verified_share"], "cited_share": calc["cited_share"],
            "complete": calc["complete"], "text_matches_scores": calc["text_matches_scores"],
        }
    verdict.pop("rubric", None)
    verdict["winner_side"] = state["picked_side"] if fixed else to_side[v.winner]
    verdict["would_have_chosen_side"] = to_side[v.would_have_chosen]
    # The finished text replaces whatever the judge streamed (deanonymized, and with any scoring note), so a client
    # that missed the live tokens still gets the whole answer here.
    await d.emitter.emit(
        "verdict_ready",
        {
            "turn_id": turn_id(_did(config), "judge", "judging", 0),
            "side": "judge",
            "winner_side": verdict["winner_side"],
            "confidence": verdict["confidence"],
            "summary": verdict["summary"],
            "final_output": verdict["final_output"],
        },
        key=f"verdict:{_did(config)}",
    )
    return {
        "ab_map": ab,
        "verdict": verdict,
        "metrics": [_metric("judge", None, "judge", 0, t0)],
        "usage": usage_record(v.usage, role="judge", phase="judge", round=0),
    }


async def finalize(state: DebateState, config: RunnableConfig) -> dict[str, Any]:
    d = _deps(config)
    did = _did(config)
    v = state["verdict"]
    pool = state.get("evidence_pool", {})
    cited = sorted(
        {e for t in state["turns"] if t["phase"] != "research" for c in t["claims"] for e in c["evidence_ids"] if e in pool}
    )
    payload = {
        "proposition": state["proposition"],
        "winner": v["winner_side"],
        "confidence": v["confidence"],
        "summary": v["summary"],
        "final_output": v["final_output"],
        "rationale": v["rationale"],
        "scores": v["scores"],
        "strongest_counterpoints": v["strongest_counterpoints"],
        "verdict_flips_if": v["verdict_flips_if"],
        "judge_would_have_chosen": v["would_have_chosen_side"],
        "citations": [pool[e] for e in cited],
        "clarifications": state.get("user_context", []),
        "end_reason": state["end_reason"],
        "picked_side": state.get("picked_side"),
        "timings": state.get("metrics", []),
        "timing_summary": summarize_timings(state.get("metrics", [])),
        "usage": state.get("usage", []),
        "usage_summary": summarize_usage(state.get("usage", [])),
    }
    node_id = await d.writer.create_result(did, payload)
    await d.emitter.emit("completed", {"node_id": node_id}, key=f"completed:{did}")
    return {"result_node_id": node_id}


def build_graph(checkpointer: Any) -> Any:
    g = StateGraph(DebateState)
    g.add_node("intake", intake)
    g.add_node("frame", frame)
    g.add_node("ask_frame", ask_frame)
    g.add_node("reframe", reframe)
    g.add_node("advance", advance)
    g.add_node("debater", build_debater())
    g.add_node("verify", verify)
    g.add_node("judge", judge)
    g.add_node("finalize", finalize)
    g.add_edge(START, "intake")
    g.add_edge("intake", "frame")
    g.add_conditional_edges("frame", route_after_frame, ["ask_frame", "advance"])
    g.add_edge("ask_frame", "reframe")
    g.add_edge("reframe", "advance")
    g.add_conditional_edges("advance", route_advance, ["debater", "verify"])
    g.add_edge("debater", "advance")
    g.add_edge("verify", "judge")
    g.add_edge("judge", "finalize")
    g.add_edge("finalize", END)
    return g.compile(checkpointer=checkpointer)