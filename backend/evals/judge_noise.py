"""How noisy is the judge? Re-judge one saved debate many times and compare one call against several combined.

A saved debate is the JSON written by `scripts/smoke_debate.py --dump`. The same transcript is judged `trials * k` times
(labels swapped between calls). Every call is a one-call verdict; each group of k is also combined into one verdict the
way production does it. The report shows how often each kind of verdict agrees with the most common one.
"""
from __future__ import annotations

import asyncio
import statistics
from collections import Counter
from typing import Any

from debate.judge_view import build_judge_view
from debate.scoring import combine_samples, sample_to_sides, score_rubric


def state_from_dump(dump: dict[str, Any]) -> dict[str, Any]:
    res = dump["result"]
    return {"turns": dump["turns"], "evidence_pool": dump.get("evidence_pool") or {}, "proposition": res["proposition"],
            "context_text": "", "user_context": res.get("clarifications") or [], "citation_report": {}}


async def _once(brain: Any, state: dict[str, Any], ab: dict[str, str]) -> dict[str, Any]:
    label_of = {side: label for label, side in ab.items()}
    view = build_judge_view(state, label_of)
    v = await brain.judge(view, None)
    return sample_to_sides(score_rubric(v.rubric, view.claims, view.cite_stats), ab)


async def measure(brain: Any, state: dict[str, Any], *, trials: int = 4, k: int = 3, concurrency: int = 6) -> dict[str, Any]:
    flip = {"A": "for", "B": "against"}, {"A": "against", "B": "for"}
    sem = asyncio.Semaphore(concurrency)

    async def run(i: int) -> dict[str, Any]:
        async with sem:
            return await _once(brain, state, flip[i % 2])

    singles = await asyncio.gather(*[run(i) for i in range(trials * k)])
    groups = [singles[g * k:(g + 1) * k] for g in range(trials)]
    one = [combine_samples([s]) for s in singles]
    many = [combine_samples(g) for g in groups]

    def describe(rs: list[dict[str, Any]]) -> dict[str, Any]:
        winners = [r["judged"] for r in rs]
        modal, n_modal = Counter(winners).most_common(1)[0]
        signed = [r["totals"]["for"] - r["totals"]["against"] for r in rs]
        return {"n": len(rs), "winners": dict(Counter(winners)), "agree_with_modal": n_modal / len(rs),
                "gap_mean": round(statistics.mean(signed), 2), "gap_sd": round(statistics.pstdev(signed), 2),
                "confidence_mean": round(statistics.mean(r["confidence"] for r in rs), 2)}

    return {"one_call": describe(one), f"combined_{k}": describe(many), "judge_calls": trials * k}


def render(report: dict[str, Any]) -> str:
    lines = ["| verdict from | n | winners | agree with most common | lead (FOR minus AGAINST) mean | lead SD | mean confidence |", "|---|---|---|---|---|---|---|"]
    for name, r in report.items():
        if not isinstance(r, dict):
            continue
        lines.append(f"| {name} | {r['n']} | {r['winners']} | {100 * r['agree_with_modal']:.0f}% | {r['gap_mean']} | {r['gap_sd']} | {r['confidence_mean']} |")
    lines.append(f"\n{report['judge_calls']} judge calls. A smaller lead SD and a higher 'agree' for the combined row is the improvement.")
    return "\n".join(lines)
