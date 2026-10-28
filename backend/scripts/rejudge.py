"""Measure judge noise on a saved debate: one call vs several combined.

    python3 scripts/smoke_debate.py --topic "..." --for-model ... --against-model ... --judge-model openai/gpt-6-luna --dump runs/d1.json
    python3 scripts/rejudge.py --dump runs/d1.json --judge-model openai/gpt-6-luna --trials 4 --k 3

Costs about $0.004 per judge call, so the default (12 calls) is about 5 cents. Reads OPENROUTER_DEBATE_API_KEY from .env.
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
from evals.judge_noise import measure, render, state_from_dump


async def main(a: argparse.Namespace) -> None:
    key = os.environ.get("OPENROUTER_DEBATE_API_KEY")
    if not key:
        sys.exit("OPENROUTER_DEBATE_API_KEY is not set (put it in .env)")
    dump = json.loads(Path(a.dump).read_text())
    client = OpenRouterClient(key, reasoning_effort=os.environ.get("DEBATE_REASONING_EFFORT") or None)
    brain = OpenRouterBrain(client, for_model=a.judge_model, against_model=a.judge_model, judge_model=a.judge_model)
    rep = await measure(brain, state_from_dump(dump), trials=a.trials, k=a.k)
    print(render(rep))
    if a.out:
        Path(a.out).write_text(json.dumps(rep, indent=1))
    await client._http.aclose()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--dump", required=True, help="JSON written by smoke_debate.py --dump")
    p.add_argument("--judge-model", required=True)
    p.add_argument("--trials", type=int, default=4, help="how many combined verdicts to produce")
    p.add_argument("--k", type=int, default=3, help="judge calls per combined verdict")
    p.add_argument("--out")
    asyncio.run(main(p.parse_args()))
