from __future__ import annotations

import asyncio
import time
from typing import Any, Optional

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send, interrupt

from .deps import AgentContext, Deps
from .judge_view import build_judge_view
from .framing import choose_questions
from .branching import assign_ids, open_questions, to_rows
from .scoring import NO_WINNER_CONFIDENCE_CAP, combine_samples, sample_to_sides, score_rubric
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
    first = {"A": "for", "B": "against"} if d.rng.random() < 0.5 else {"A": "against", "B": "for"}
    if not any(t["phase"] != "research" for t in state.get("turns", [])):
        # stopped before anyone argued: nothing to judge, and no model call to pay for
        verdict = {
            "winner_side": "no_clear_winner", "would_have_chosen_side": "no_clear_winner", "confidence": 0.0,
            "rationale": "The debate was ended before either side made an argument.",
            "summary": "The debate was ended before either side made an argument, so there is no verdict.",
            "final_output": "No arguments were made, so there is no conclusion to report. Start the debate again to get one.",
            "scores": {}, "strongest_counterpoints": [], "verdict_flips_if": [],
        }
        return {"ab_map": first, "verdict": verdict, "metrics": [_metric("judge", None, "judge", 0, t0)]}

    # The judge runs `judge_samples` times, with the A/B labels swapped between runs so position bias cancels. The runs
    # are independent and concurrent; only the first streams live text. See scoring.combine_samples.
    n = max(1, int(d.judge_samples))
    swapped = {"A": first["B"], "B": first["A"]}
    abs_ = [first if i % 2 == 0 else swapped for i in range(n)]

    async def one(i: int) -> tuple[Any, Any, Optional[str]]:
        label_of = {side: label for label, side in abs_[i].items()}
        view = build_judge_view(dict(state), label_of)
        fixed = label_of[state["picked_side"]] if state.get("end_reason") == "user_picked" else None
        sink = make_sink(d, _did(config), "judge", "judging", 0) if i == 0 else None
        try:
            v = await (d.brain.judge(view, fixed, sink) if sink is not None else d.brain.judge(view, fixed))
        finally:
            if sink is not None:
                await sink.close()
        return v, view, fixed

    got = await asyncio.gather(*[one(i) for i in range(n)], return_exceptions=True)
    ok = [(i, r) for i, r in enumerate(got) if not isinstance(r, BaseException)]
    if not ok:
        raise next(r for r in got if isinstance(r, BaseException))
    usage: list[dict[str, Any]] = []
    for _, (sv, _view, _fx) in ok:
        usage += usage_record(sv.usage, role="judge", phase="judge", round=0)

    fixed = ok[0][1][2]
    samples = []
    for i, (sv, view, fx) in ok:
        if sv.rubric:
            calc_i = score_rubric(sv.rubric, view.claims, view.cite_stats, fx)
            samples.append((i, sample_to_sides(calc_i, abs_[i]), calc_i))
    if samples:
        comb = combine_samples([s for _, s, _ in samples])
        wi, _, wcalc = samples[comb["writer"]]
        ab = abs_[wi]
        v, view, _ = dict(ok)[wi]
        label_of = {side: label for label, side in ab.items()}
        # The combined result in the writer sample's A/B labels, so the code below is the same for one sample or many.
        calc = {
            **wcalc,
            "winner": fixed or (label_of[comb["judged"]] if comb["judged"] != "none" else "none"),
            "would_have_chosen": label_of[comb["judged"]] if comb["judged"] != "none" else "none",
            "confidence": comb["confidence"],
            "totals": {label_of[s]: x for s, x in comb["totals"].items()},
            "criteria": {label_of[s]: x for s, x in comb["criteria"].items()},
            "gap": comb["gap"], "coverage": comb["coverage"], "complete": comb["complete"],
            "verified_share": comb["verified_share"], "cited_share": comb["cited_share"],
            "text_matches_scores": comb["text_matches_scores"],
        }
        v = v.model_copy(update={
            "winner": calc["winner"], "would_have_chosen": calc["would_have_chosen"],
            "confidence": calc["confidence"], "scores": dict(calc["totals"]),
        })
    else:
        # A brain that returns no rubric (a scripted fake): use the first answer as it is.
        wi = ok[0][0]
        ab = abs_[wi]
        v, view, _ = ok[0][1]
        label_of = {side: label for label, side in ab.items()}
        calc = comb = None

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
            "judge_samples": comb["samples"], "agreement": comb["agreement"], "gap_spread": comb["gap_spread"],
        }
    verdict.pop("rubric", None)
    verdict["winner_side"] = state["picked_side"] if fixed else to_side[v.winner]
    verdict["would_have_chosen_side"] = to_side[v.would_have_chosen]

    # Does the finished text actually argue for the side the rubric picked? The judge's own `leaning` field cannot answer
    # that: it has disagreed with its own prose (rubric FOR, prose "the evidence does not support the claim"), and the
    # leaning-vs-rubric check passed because the leaning matched. So the text is read on its own, by a separate call that
    # sees only the proposition and the verdict. A mismatch does not change the winner -- the rubric still decides -- but
    # it is recorded and the reader is told, because a card that contradicts itself is worse than one that admits a split.
    prose_says = None
    if calc and not fixed and hasattr(d.brain, "check_conclusion"):
        try:
            prose_says, usage_cc = await d.brain.check_conclusion(state["proposition"], verdict["final_output"])
            usage += usage_record(usage_cc, role="judge", phase="conclusion_check", round=0)
        except Exception:
            prose_says = None  # the guard is best-effort: never fail a finished debate over it
    if prose_says in ("supported", "not_supported", "neither"):
        implied = {"supported": "for", "not_supported": "against", "neither": "no_clear_winner"}[prose_says]
        verdict["scores"]["rubric"]["prose_conclusion"] = implied
        verdict["scores"]["rubric"]["prose_matches_winner"] = implied == verdict["winner_side"]
        # Only an *opposite* conclusion is a contradiction. A verdict that weighs both sides without committing is the
        # normal case and the whole reason the winner is computed rather than written: the judge supplies the analysis,
        # the rubric resolves it. Treating "didn't commit" as a contradiction made 4 of 6 open-question debates report no
        # winner, which throws away the one thing the orchestration reliably provides. So the override fires only when
        # both readings name a side and they name different ones.
        definite = {"for", "against"}
        contradicts = implied in definite and verdict["winner_side"] in definite and implied != verdict["winner_side"]
        verdict["scores"]["rubric"]["prose_contradicts_winner"] = contradicts
        if contradicts:
            verdict["scores"]["rubric"]["text_matches_scores"] = False
            verdict["winner_side"] = "no_clear_winner"
            verdict["confidence"] = min(float(verdict.get("confidence") or 0.0), NO_WINNER_CONFIDENCE_CAP)
            verdict["final_output"] = (
                "**No clear winner.** The scored comparison and the written analysis below argued for different sides, "
                "so neither is reported as winning. The analysis is unchanged.\n\n" + verdict["final_output"])
    if calc and not fixed and not verdict["scores"]["rubric"]["text_matches_scores"] and prose_says is None:
        # The judge's own leaning disagreed with its totals and the independent check was unavailable.
        verdict["final_output"] = (
            "**Treat this verdict with caution.** The judge's scoring and its written reasoning did not fully agree; "
            "the winner shown follows the scores.\n\n" + verdict["final_output"])
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
        "usage": usage,
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
    # The questions worth exploring next, as nodes. A separate small call rather than more work for the judge: the judge
    # is already the longest call in the run and has produced self-contradictory output when overloaded. Best-effort --
    # a brain without the method, or a reply that cannot be read, simply yields no branches and never fails a debate.
    branches: list[dict[str, Any]] = []
    branch_usage: list[dict[str, Any]] = []
    argued = any(t["phase"] != "research" for t in state.get("turns", []))
    if argued and d.max_branches > 0 and hasattr(d.brain, "propose_branches"):
        try:
            got, bu = await d.brain.propose_branches(
                payload["proposition"], payload["summary"], open_questions(payload["final_output"]),
                payload.get("verdict_flips_if") or [], payload.get("strongest_counterpoints") or [],
                max_branches=d.max_branches,
            )
            branches = to_rows(assign_ids(got))
            branch_usage = usage_record(bu, role="judge", phase="branches", round=0)
        except Exception:
            branches = []
    payload["branches"] = branches
    if branch_usage:
        payload["usage"] = (payload.get("usage") or []) + branch_usage
        payload["usage_summary"] = summarize_usage(payload["usage"])

    node_id = await d.writer.create_result(did, payload)
    await d.emitter.emit("completed", {"node_id": node_id, "branches": len(branches)}, key=f"completed:{did}")
    return {"result_node_id": node_id, "usage": branch_usage}


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
