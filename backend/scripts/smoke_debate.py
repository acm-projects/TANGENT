"""Run one real debate in-process on YOUR machine. No database, no AWS, no queue.

Reads OPENROUTER_DEBATE_API_KEY and S2_API_KEY from the environment or a .env file (never printed).
Questions from the agents are answered at the terminal. Example:

    python scripts/smoke_debate.py --topic "MacBook Air vs MacBook Pro for a CS student" \
        --for-model anthropic/claude-haiku-5.5 --against-model anthropic/claude-haiku-5.5 --judge-model openai/gpt-6-luna \
        --rounds 2 --max-cost 1.00

Prints each turn's thinking and argument as it arrives, the verdict, timings by phase, token usage and cost, and a
QUALITY SCORECARD (concessions, hedging, invented numbers and quotes, citation hygiene, judge structure, repair retries, cost).
Compare scorecards between runs after a prompt or model change; --dump saves it with the transcript.

Unattended (for Claude Code or CI): add --auto-answer (agents' questions get the first option) and --check
(asserts the invariants below and exits 1 on failure). --offline uses a scripted fake model, so you can verify the
script and the graph with no keys at all. --events-out saves every event in the order the SSE stream would send it.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    from dotenv import find_dotenv, load_dotenv

    load_dotenv(find_dotenv(usecwd=True))
except ImportError:
    pass

from langgraph.checkpoint.memory import InMemorySaver

from debate.deps import Deps
from debate.fakes import InMemoryControl, InMemoryEmitter, InMemoryWriter
from debate.graph import build_graph
from debate.openrouter import OpenRouterBrain, OpenRouterClient
from debate.quality import render as render_card
from debate.quality import scorecard, summarize
from debate.runner import build_resume, merge_pending, run_segment
from debate.search_s2 import SemanticScholarSearch


class PrintingEmitter(InMemoryEmitter):
    async def emit(self, type, payload, key=None):
        new = await super().emit(type, payload, key)
        if new and type == "turn_completed":
            print(f"\n=== {payload['side'].upper()} | {payload['phase']} {payload['round']} ===")
            for t in payload.get("thinking") or []:
                print(f"  (thinking) {t}")
            print(payload["argument"])
        elif new and type in ("tool_called", "phase_changed", "control_applied"):
            print(f"[{type}] {json.dumps(payload)[:200]}")
        return new


def ask(questions, auto=False):
    answers = {}
    for q in questions:
        print(f"\n? {q['prompt']}")
        opts = q.get("options") or []
        for i, o in enumerate(opts, 1):
            print(f"   {i}. {o['label']}")
        if auto:
            answers[q["id"]] = opts[0]["label"] if opts else "no preference"
            print(f"> (auto) {answers[q['id']]}")
            continue
        raw = input("> ").strip()
        answers[q["id"]] = opts[int(raw) - 1]["label"] if raw.isdigit() and 0 < int(raw) <= len(opts) else raw
    return answers


def check(a, state, result, events, deps) -> list[tuple[bool, str]]:
    turns = state.get("turns", [])
    by = lambda phase: [t for t in turns if t["phase"] == phase]
    pool = state.get("evidence_pool", {})
    cited = {e for t in turns if t["phase"] != "research" for c in t["claims"] for e in c["evidence_ids"]}
    types = [e["type"] for e in events]
    out = [
        (result["winner"] in ("for", "against", "no_clear_winner"), f"winner is valid ({result['winner']})"),
        (bool(result["summary"].strip()) and bool(result["final_output"].strip()), "summary and final_output are not empty"),
        (0.0 <= result["confidence"] <= 1.0, "confidence is between 0 and 1"),
        (len(by("research")) == 2 and len(by("opening")) == 2 and len(by("closing")) == 2, "research, opening and closing ran for both sides"),
        (len(by("rebuttal")) == 2 * a.rounds, f"{a.rounds} rebuttal round(s) ran for both sides"),
        (all(t["argument"].strip() for t in turns), "no empty arguments"),
        (all(t["thinking"] for t in turns), "every turn streamed at least one thinking note"),
        (cited <= set(pool), f"every cited evidence id exists in the pool ({len(cited - set(pool))} unverified)"),
        (not any(t.get("truncated") and ("could not be produced" in t["argument"] or not t["argument"].strip()) for t in turns), "no turn forced by the step cap came back empty or skipped"),
        (types.count("turn_completed") == len(turns), "one turn_completed event per turn"),
        (bool(result.get("timing_summary")) and bool(result.get("usage_summary")), "timings and usage were recorded"),
        (all(b.get("id") and b.get("title") and b.get("question") and b.get("why") for b in (result.get("branches") or [])),
         f"every proposed branch is complete ({len(result.get('branches') or [])} branch(es))"),
    ]
    if not a.offline:
        out.append((float((result["usage_summary"].get("total") or {}).get("cost") or 0) > 0, "OpenRouter reported a cost"))
    return out


async def main(a: argparse.Namespace) -> None:
    context = Path(a.context_file).read_text() if a.context_file else ""
    if a.offline:
        from debate.fakes import FakeSearch, ScriptedBrain
        from debate.schemas import Question

        client = None
        from debate.schemas import Branch

        brain = ScriptedBrain(frame_questions=[Question(id="q1", prompt="What is your budget?", options=[{"label": "<$1k"}, {"label": "$1k+"}])])
        # scripted so --offline exercises branching too; the real brain writes these from the finished verdict
        brain.branches = [
            Branch(title="Delivery speed vs operating cost",
                   question="Does the faster option stay faster once the operating burden is counted?",
                   why="Neither side measured both together.", kind="research"),
            Branch(title="When the benefit starts",
                   question="At what team size does the advantage begin to pay for itself?",
                   why="Both sides asserted it without a timeline.", kind="research"),
            Branch(title="Cost of changing course later",
                   question="How expensive is switching approach at year two?",
                   why="Never compared against committing from day one.", kind="debate"),
        ]
        search = FakeSearch()
    else:
        key = os.environ.get("OPENROUTER_DEBATE_API_KEY")
        if not key:
            sys.exit("OPENROUTER_DEBATE_API_KEY is not set (put it in .env)")
        if not (a.for_model and a.against_model and a.judge_model):
            sys.exit("--for-model, --against-model and --judge-model are required (or use --offline)")
        client = OpenRouterClient(key, reasoning_effort=a.reasoning_effort)
        brain = OpenRouterBrain(client, for_model=a.for_model, against_model=a.against_model, judge_model=a.judge_model)
        search = None

    async def loader(_id):
        return context, []

    class NoSearch:
        async def search(self, query):
            return []

    deps = Deps(
        brain=brain,
        search=search or (NoSearch() if a.no_search else SemanticScholarSearch(os.environ.get("S2_API_KEY"))),
        control=InMemoryControl(),
        emitter=PrintingEmitter(),
        context_loader=loader,
        writer=InMemoryWriter(),
        rng=random.Random(),
        max_cost_usd=a.max_cost,
        judge_samples=a.judge_samples,
    )
    graph = build_graph(InMemorySaver())
    cfg = {"configurable": {"thread_id": "smoke", "deps": deps}, "recursion_limit": 200}
    graph_input = {"debate_id": "smoke", "topic": a.topic, "rounds": a.rounds}
    while True:
        seg = await run_segment(graph, cfg, graph_input)
        graph_input = None
        if seg.status == "done":
            break
        if seg.status == "paused":
            graph_input = build_resume(seg.interrupts, ask(merge_pending(seg.interrupts), a.auto_answer))
    state = (await graph.aget_state(cfg)).values
    result = deps.writer.results["smoke"]
    print("\n\n######## VERDICT ########")
    print(f"winner={result['winner']} confidence={result['confidence']} end_reason={result['end_reason']}")
    print(result["summary"], "\n\n", result["final_output"])
    print("\n######## TIMING (ms) ########")
    print(json.dumps(result.get("timing_summary"), indent=1)[:3000])
    print("\n######## USAGE ########")
    print(json.dumps(result.get("usage_summary"), indent=1)[:3000])
    card = scorecard(state, result, deps.emitter.events, context=context, rounds=a.rounds)
    print("\n######## QUALITY SCORECARD (heuristics: WARN means read that part of the transcript) ########")
    print(render_card(card))
    if a.dump:
        Path(a.dump).write_text(json.dumps({"result": result, "turns": state.get("turns"), "evidence_pool": state.get("evidence_pool"), "scorecard": card}, indent=1, default=str))
        print(f"\nfull output written to {a.dump}")
    if a.events_out:
        Path(a.events_out).write_text(json.dumps(deps.emitter.events, indent=1, default=str))
        print(f"{len(deps.emitter.events)} events written to {a.events_out}")
    if client:
        await client._http.aclose()
    if a.check:
        print("\n######## CHECKS ########")
        results = check(a, state, result, deps.emitter.events, deps)
        for ok, label in results:
            print(("PASS  " if ok else "FAIL  ") + label)
        if not all(ok for ok, _ in results):
            sys.exit(1)
    if a.strict_quality and summarize(card)["warn"]:
        sys.exit(1)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--topic", required=True)
    p.add_argument("--for-model")
    p.add_argument("--against-model")
    p.add_argument("--judge-model")
    p.add_argument("--offline", action="store_true", help="scripted fake model, no keys, no network")
    p.add_argument("--auto-answer", action="store_true", help="answer agent questions with the first option")
    p.add_argument("--check", action="store_true", help="assert invariants, exit 1 on failure")
    p.add_argument("--strict-quality", action="store_true", help="exit 1 if the quality scorecard has any WARN (it always prints)")
    p.add_argument("--events-out", help="write every event (SSE order) to this JSON file")
    p.add_argument("--rounds", type=int, default=2, choices=[1, 2, 3])
    p.add_argument("--reasoning-effort", choices=["low", "medium", "high"], default=os.environ.get("DEBATE_REASONING_EFFORT") or None, help="ask models to reason less/more (default: $DEBATE_REASONING_EFFORT, else each model's own default)")
    p.add_argument("--context-file", help="text file standing in for earlier chats")
    p.add_argument("--judge-samples", type=int, default=3, help="how many times the judge runs (labels swapped between runs) and is combined in code; 1 = a single call")
    p.add_argument("--no-search", action="store_true")
    p.add_argument("--max-cost", type=float, default=None)
    p.add_argument("--dump", help="write the full result JSON here")
    args = p.parse_args()
    if not args.topic.strip():
        sys.exit('--topic is empty. In a new terminal, set it first: TOPIC="Is X better than Y for Z?" (shell variables do not survive a new window)')
    asyncio.run(main(args))
