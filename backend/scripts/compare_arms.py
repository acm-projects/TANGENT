"""Does the debate beat one plain model call? Run both on the same questions and count.

Claims with a known true/false answer are scored by accuracy (no judge involved). Open questions are graded blind, pairwise,
by models from other families. Results are saved as they come, so a stopped run carries on if you repeat the command.

    # 1. a free offline check that everything is wired (scripted fake models, no keys, no network)
    python3 scripts/compare_arms.py --offline --claims evals/data/claims_smoke.jsonl --topics evals/data/topics_example.jsonl --out runs/eval_offline

    # 2. real claims with expert labels (one-time download of SciFact, a few MB)
    python3 scripts/compare_arms.py --fetch-scifact evals/data/scifact

    # 3. the experiment (claims: accuracy; topics: blind grading)
    python3 scripts/compare_arms.py --claims evals/data/scifact/scifact_claims.jsonl --n 40 \
        --topics evals/data/topics_example.jsonl --arms single,cot,rag,vote,debate \
        --model anthropic/claude-haiku-5.5 --debate-judge openai/gpt-6-luna --graders <model-from-another-family>[,<another>] \
        --out runs/eval_1

    # 4. just rebuild the report from saved results
    python3 scripts/compare_arms.py --report-only --claims ... --topics ... --out runs/eval_1

Cost: a debate is about $0.05-0.07 and 3-4 minutes; a single call is a fraction of a cent. 40 claims + 6 topics in all five arms is
roughly $3-4 and under an hour at --concurrency 3. Use --max-cost to cap a single debate.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    from dotenv import find_dotenv, load_dotenv

    load_dotenv(find_dotenv(usecwd=True))
except ImportError:
    pass

from debate.openrouter import OpenRouterBrain, OpenRouterClient
from debate.search_s2 import CachedSearch, SemanticScholarSearch
from evals import datasets
from evals.arms import DebateArm, RagArm, SelfDebateArm, SingleArm, VoteArm, make_polarity_check
from evals.export import write as write_export
from evals.report import render
from evals.runner import Store, grade_topics, run_arms

ALL_ARMS = ("single", "cot", "rag", "vote", "selfdebate", "selfdebate_rag", "debate")


def load_items(a: argparse.Namespace) -> list[datasets.Item]:
    items: list[datasets.Item] = []
    for path in (a.claims, a.topics):
        if path:
            items += datasets.sample(datasets.load(path), a.n, a.seed)
    return items


async def maybe_negate(a: argparse.Namespace, items: list[datasets.Item], client, model: str) -> list[datasets.Item]:
    """With --negate, swap in the negated claims (correct answers flip) and save them for inspection."""
    if not a.negate:
        return items
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    cached = out / "negated_claims.jsonl"
    if cached.exists():
        items = datasets.load(cached)
        print(f"reusing {len(items)} negated claims from {cached}")
        return items
    negated, cost = await datasets.negate(client, model, items)
    dropped = len(items) - len(negated)
    cached.write_text("\n".join(json.dumps({"id": i.id, "text": i.text, "label": i.label}) for i in negated) + "\n")
    print(f"negated {len(negated)} claims (${cost:.4f}"
          + (f", {dropped} dropped because the negation could not be read" if dropped else "") + f"); saved to {cached}")
    print("Read that file before trusting the run: a bad negation is a mislabelled claim.")
    return negated


def build(a: argparse.Namespace):
    """Returns (arms, grading client, polarity/other client)."""
    wanted = [x.strip() for x in a.arms.split(",") if x.strip()]
    bad = [x for x in wanted if x not in ALL_ARMS]
    if bad:
        sys.exit(f"unknown arm(s): {', '.join(bad)}. Choose from {', '.join(ALL_ARMS)}")
    if a.offline:
        from debate.fakes import FakeSearch, ScriptedBrain
        from evals.fakes import FakeClient

        client = high = FakeClient()
        search = FakeSearch()
        make_brain = lambda: ScriptedBrain()  # noqa: E731
    else:
        key = os.environ.get("OPENROUTER_DEBATE_API_KEY")
        if not key:
            sys.exit("OPENROUTER_DEBATE_API_KEY is not set (put it in .env)")
        if not a.model or not a.debate_judge:
            sys.exit("--model and --debate-judge are required (or use --offline)")
        effort = os.environ.get("DEBATE_REASONING_EFFORT") or None
        client = OpenRouterClient(key, reasoning_effort=effort)
        high = OpenRouterClient(key, reasoning_effort="high")
        search = CachedSearch(SemanticScholarSearch(os.environ.get("S2_API_KEY")))
        make_brain = lambda: OpenRouterBrain(client, for_model=a.model, against_model=a.model, judge_model=a.debate_judge)  # noqa: E731
    model = a.model or "fake"
    arms: dict = {}
    for name in wanted:
        if name == "single":
            arms[name] = SingleArm(client, model, name="single")
        elif name == "cot":
            arms[name] = SingleArm(high, model, name="cot", max_tokens=8000)
        elif name == "rag":
            arms[name] = RagArm(client, model, search)
        elif name == "selfdebate":
            arms[name] = SelfDebateArm(client, model)
        elif name == "selfdebate_rag":
            arms[name] = SelfDebateArm(client, model, search, name="selfdebate_rag")
        elif name == "vote":
            arms[name] = VoteArm(client, model, k=a.vote_k)
        elif name == "debate":
            arms[name] = DebateArm(make_brain, search, rounds=a.rounds, judge_samples=a.judge_samples, max_cost=a.max_cost,
                                   polarity_check=make_polarity_check(client, model))
    return arms, client, high


async def main(a: argparse.Namespace) -> None:
    items = load_items(a)
    if not items:
        sys.exit("give --claims and/or --topics")
    store = Store(a.out)
    errors: list[str] = []
    client = None
    if not a.report_only:
        arms, client, high = build(a)
        items = await maybe_negate(a, items, client, a.model or "fake")
        if not items:
            sys.exit("no questions left after negation")
        print(f"{len(items)} questions, arms: {', '.join(arms)}, results in {a.out}")
        errors += await run_arms(items, arms, store, concurrency=a.concurrency, match_length=not a.no_match_length)
        if "debate" in arms and any(not i.label for i in items):
            graders = [g.strip() for g in (a.graders or "").split(",") if g.strip()]
            if not graders and not a.offline:
                print("no --graders given, so open questions are not graded (claims are scored without any judge).")
            else:
                against = [x.strip() for x in (a.grade_vs or "").split(",") if x.strip()] or None
                unknown = [x for x in (against or []) if x not in arms]
                if unknown:
                    sys.exit(f"--grade-vs names arm(s) not in this run: {', '.join(unknown)}")
                errors += await grade_topics(items, store, client, graders or ["fake-grader"],
                                             y_arms=against, dry_run=a.dry_run_grading,
                                             concurrency=a.grader_concurrency, max_tokens=a.grader_max_tokens)
    text = render(items, store, errors)
    print("\n" + text)
    (Path(a.out) / "report.md").write_text(text)
    files = write_export(items, store, a.out)
    print(f"\nreport saved to {Path(a.out) / 'report.md'}")
    print("data files: " + ", ".join(str(v) for v in files.values()))
    if client is not None and hasattr(client, "_http"):
        await client._http.aclose()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Compare the debate with single-call baselines.")
    p.add_argument("--fetch-scifact", metavar="DIR", help="download SciFact and write DIR/scifact_claims.jsonl, then exit")
    p.add_argument("--per-label", type=int, default=100, help="with --fetch-scifact: claims kept per label")
    p.add_argument("--claims", help="JSONL of claims with labels")
    p.add_argument("--topics", help="JSONL of open questions")
    p.add_argument("--n", type=int, help="use a reproducible sample of this many per file")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--arms", default="single,cot,rag,selfdebate,selfdebate_rag,debate", help=f"comma list from: {', '.join(ALL_ARMS)}")
    p.add_argument("--model", help="the answering model and both debaters, e.g. anthropic/claude-haiku-5.5")
    p.add_argument("--debate-judge", help="the debate's judge model, e.g. openai/gpt-6-luna")
    p.add_argument("--graders", help="comma list of grader models (use a family that wrote none of the answers)")
    p.add_argument("--grade-vs", help="only grade the debate against these arms, e.g. 'single,selfdebate_rag'. Grading is "
                   "questions x pairs x graders x 2 calls and is nearly all of a topics run's cost, so narrowing this is "
                   "the cheapest saving available. Default: every other arm in the run.")
    p.add_argument("--grader-max-tokens", type=int, default=None, help="token budget per grader call (default 3000, "
                   "retried at double up to 12000). Raise it if replies come back empty with finish_reason=length: "
                   "a grader that reasons before answering spends most of its budget before writing the JSON.")
    p.add_argument("--grader-concurrency", type=int, default=3, help="grader pairs in flight at once. Each pair is "
                   "graders x 2 calls, so the real request count is this x that. Lower it if replies start failing.")
    p.add_argument("--dry-run-grading", action="store_true", help="run the arms, print how many grader calls grading would "
                   "take, and stop before sending any. Use this to check the bill first.")
    p.add_argument("--rounds", type=int, default=2, choices=[1, 2, 3])
    p.add_argument("--judge-samples", type=int, default=3)
    p.add_argument("--vote-k", type=int, default=9)
    p.add_argument("--concurrency", type=int, default=2, help="questions in flight at once (debates share one search rate limit)")
    p.add_argument("--max-cost", type=float, default=None, help="stop a single debate if it passes this many dollars")
    p.add_argument("--no-match-length", action="store_true", help="do not tell single-call arms to answer at the debate answer's length")
    p.add_argument("--out", default="runs/eval")
    p.add_argument("--negate", action="store_true", help="negate every claim (correct answers flip to the opposite label). Isolates judge side bias from claim difficulty; use a separate --out")
    p.add_argument("--offline", action="store_true", help="scripted fake models: checks the wiring, says nothing about quality")
    p.add_argument("--report-only", action="store_true", help="rebuild the report from saved results")
    args = p.parse_args()
    if args.fetch_scifact:
        print("wrote", datasets.fetch_scifact(args.fetch_scifact, per_label=args.per_label, seed=args.seed))
        sys.exit(0)
    asyncio.run(main(args))
