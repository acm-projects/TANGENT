"""Pick a grader model for the topics run: list the cheap candidates on your account, then verify one works.

The grader's job is narrow -- read two answers and say which is better on five criteria, as JSON. It needs reliable
structured output and enough context for two ~900-word answers. It does not need frontier reasoning or domain knowledge,
so the cheapest competent model wins. It must sit outside the families that wrote the answers (Anthropic debaters, OpenAI
judge), because models tend to prefer their own family's style.

    python3 scripts/pick_grader.py                      # candidates, cheapest first
    python3 scripts/pick_grader.py --test <model-id>     # one real grader call (~$0.001): does it return usable JSON?

Reads OPENROUTER_DEBATE_API_KEY from the environment or .env.
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

import httpx

# Families that wrote none of the answers. Order is my preference for this task, best first:
# Gemini Flash-class models are usually the cheapest reliable JSON producers; DeepSeek is strong and very cheap;
# Llama / Mistral / Qwen / Grok are fine fallbacks.
PREFERRED = ("google/", "deepseek/", "nvidia/", "meta-llama/", "mistralai/", "qwen/", "x-ai/")
EXCLUDE_WORDS = ("free", "vision", "embed", "rerank", "tts", "whisper", "image", "guard", "coder", "math")
# A vision-language variant works for text-only grading but is built for something else, so prefer a plain text sibling
# of the same generation when one exists. Not excluded: the price is often better and the task is not demanding.
DEPRIORITIZE_SUFFIXES = ("-vl", "-vision")
MIN_CONTEXT = 16000  # two long answers plus the prompt


def _price_per_m(p: dict, key: str) -> float | None:
    try:
        return float(p.get(key, "")) * 1_000_000
    except (TypeError, ValueError):
        return None


def candidates(models: list[dict]) -> list[dict]:
    out = []
    for m in models:
        mid = str(m.get("id", ""))
        if not mid.startswith(PREFERRED):
            continue
        low = mid.lower()
        if any(w in low for w in EXCLUDE_WORDS):
            continue
        if int(m.get("context_length") or 0) < MIN_CONTEXT:
            continue
        pin = _price_per_m(m.get("pricing") or {}, "prompt")
        pout = _price_per_m(m.get("pricing") or {}, "completion")
        if pin is None or pout is None or pin <= 0:
            continue  # unpriced or free tiers are rate-limited and unreliable for a batch run
        out.append({"id": mid, "in": pin, "out": pout, "context": int(m.get("context_length") or 0),
                    "rank": PREFERRED.index(next(f for f in PREFERRED if mid.startswith(f))),
                    "vl": low.endswith(DEPRIORITIZE_SUFFIXES)})
    out.sort(key=lambda r: (r["in"] + r["out"], r["vl"], r["rank"]))
    return out


def estimate(row: dict, calls: int = 24, in_tokens: int = 2600, out_tokens: int = 200) -> float:
    """A grader call carries the question plus two full answers; ~2.6k in, ~200 out is what the runs so far look like."""
    return calls * (in_tokens * row["in"] + out_tokens * row["out"]) / 1_000_000


async def main(a: argparse.Namespace) -> None:
    key = os.environ.get("OPENROUTER_DEBATE_API_KEY")
    if not key:
        sys.exit("OPENROUTER_DEBATE_API_KEY is not set (put it in .env)")
    async with httpx.AsyncClient(timeout=30) as http:
        if a.test:
            from debate.openrouter import OpenRouterClient
            from evals.grading import grade_pair

            client = OpenRouterClient(key, http=http)
            g = await grade_pair(client, [a.test], "t", "Is a four-day work week better for productivity?",
                                 "A", "Trials report maintained output on fewer paid hours, which implies higher output "
                                      "per hour, though most lack a five-day control group. " * 12,
                                 "B", "Shorter weeks are popular with staff. " * 12, max_tokens=a.max_tokens)
            both = g.failures == 0
            ok = not g.error and g.outcome.get("overall") in ("x", "y", "tie") and both
            print(f"model      : {a.test}")
            print(f"both calls : {'yes' if both else f'NO -- {g.failures} of 2 failed'}")
            print(f"usable JSON: {'yes' if not g.error else 'NO'}")
            if g.error or g.error_detail:
                print(f"why        : {g.error or g.error_detail}")
            print(f"picked     : {g.outcome.get('overall', '-')}   order-consistent: {g.self_consistent.get(a.test)}")
            print(f"cost       : ${g.cost:.5f} for {2 - g.failures} call(s)  ->  about "
                  f"${(g.cost / max(1, 2 - g.failures)) * a.calls:.3f} for {a.calls} calls")
            if ok:
                print(f"\nUse it:  --graders {a.test} --grade-vs single,selfdebate_rag")
            else:
                print("\nDo not use this one for a batch run yet. A model that drops calls one at a time will drop most of"
                      "\nthem under load. Retry once (it may be transient), then try the next candidate:"
                      "\n  python3 scripts/pick_grader.py")
            sys.exit(0 if ok else 1)

        r = await http.get("https://openrouter.ai/api/v1/models", headers={"Authorization": f"Bearer {key}"})
        r.raise_for_status()
        rows = candidates(r.json().get("data") or [])
    if not rows:
        sys.exit("no priced candidates found outside Anthropic/OpenAI; paste the full model list and we'll pick by hand")
    print(f"Grader candidates, cheapest first. Last column is the estimated cost of {a.calls} grader calls.\n")
    print(f"{'model':52s} {'$/M in':>8s} {'$/M out':>8s} {'context':>9s} {'~' + str(a.calls) + ' calls':>10s}")
    for row in rows[: a.limit]:
        print(f"{row['id']:52s} {row['in']:8.3f} {row['out']:8.3f} {row['context']:9d} {'$' + format(estimate(row, a.calls), '.3f'):>10s}")
    print(f"\nVerify one before the real run:  python3 scripts/pick_grader.py --test {rows[0]['id']}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--test", metavar="MODEL_ID", help="send one real grader pair to this model and report whether it works")
    p.add_argument("--calls", type=int, default=24, help="grader calls to price (default 24 = 6 topics x 2 pairs x 1 grader x 2 orders)")
    p.add_argument("--max-tokens", type=int, default=3000, help="token budget per grader call; retried at double up to 12000")
    p.add_argument("--limit", type=int, default=15)
    asyncio.run(main(p.parse_args()))
