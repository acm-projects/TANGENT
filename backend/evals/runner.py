"""Runs arms over items with a resumable on-disk cache, then grades topics pairwise. Nothing here talks to a database."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Callable, Optional

from .arms import ArmResult, words
from .datasets import Item
from .grading import PairGrade, grade_pair


class Store:
    """JSON Lines files in `out/`. A run that stops can be started again with the same --out and carries on where it left off."""

    def __init__(self, out: str | Path) -> None:
        self.dir = Path(out)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.results_path = self.dir / "results.jsonl"
        self.grades_path = self.dir / "grades.jsonl"
        self.results: dict[tuple[str, str], ArmResult] = {}
        self.grades: dict[tuple[str, str, str], PairGrade] = {}
        for line in self._lines(self.results_path):
            r = ArmResult.from_dict(json.loads(line))
            self.results[(r.arm, r.item_id)] = r
        for line in self._lines(self.grades_path):
            g = PairGrade(**json.loads(line))
            self.grades[(g.question_id, g.x_arm, g.y_arm)] = g

    @staticmethod
    def _lines(p: Path) -> list[str]:
        return [x for x in p.read_text().splitlines() if x.strip()] if p.exists() else []

    def add_result(self, r: ArmResult) -> None:
        self.results[(r.arm, r.item_id)] = r
        with self.results_path.open("a") as f:
            f.write(json.dumps(r.to_dict(), default=str) + "\n")

    def add_grade(self, g: PairGrade) -> None:
        self.grades[(g.question_id, g.x_arm, g.y_arm)] = g
        with self.grades_path.open("a") as f:
            f.write(json.dumps(g.__dict__, default=str) + "\n")


async def run_arms(items: list[Item], arms: dict[str, Any], store: Store, *, concurrency: int = 2, match_length: bool = True,
                   log: Callable[[str], None] = print) -> list[str]:
    """Runs every arm on every item (skipping what is already cached). Returns a list of error strings."""
    errors: list[str] = []
    sem = asyncio.Semaphore(max(1, concurrency))

    async def one(arm_name: str, item: Item, target: Optional[int]) -> Optional[ArmResult]:
        key = (arm_name, item.id)
        if key in store.results:
            return store.results[key]
        try:
            r = await arms[arm_name].run(item, target_words=target)
        except Exception as e:  # keep going: one bad item must not lose the rest of an expensive run
            errors.append(f"{arm_name} on {item.id}: {type(e).__name__}: {str(e)[:200]}")
            log(f"  ! {errors[-1]}")
            return None
        store.add_result(r)
        log(f"  {arm_name:7s} {item.id:10s} cost ${r.cost:.4f} {r.seconds:5.1f}s" + (f" -> {r.label}" if r.label else ""))
        return r

    async def per_item(item: Item) -> None:
        async with sem:
            target: Optional[int] = None
            if "debate" in arms:
                d = await one("debate", item, None)
                if d is not None and match_length and not item.label:
                    target = max(150, min(900, words(d.text)))
            rest = [a for a in arms if a != "debate" and not (a == "vote" and not item.label)]
            await asyncio.gather(*[one(a, item, target) for a in rest])

    await asyncio.gather(*[per_item(i) for i in items])
    return errors


async def grade_topics(items: list[Item], store: Store, client: Any, graders: list[str], *, x_arm: str = "debate",
                       y_arms: Optional[list[str]] = None, log: Callable[[str], None] = print,
                       dry_run: bool = False, concurrency: int = 3, max_tokens: Optional[int] = None) -> list[str]:
    """Grades each (question, x_arm vs y_arm) pair not already on disk.

    Grading, not the arms, is what a topics run costs: every pair is sent to every grader in both orders, so the call
    count is questions x pairs x graders x 2 and each call carries two full answers. Narrowing `y_arms` to the baselines
    that actually matter is the cheapest lever there is. `dry_run` reports the planned calls and spends nothing.
    """
    errors: list[str] = []
    arms_present = {a for (a, _i) in store.results}
    y_arms = [y for y in (y_arms or sorted(arms_present - {x_arm})) if y in arms_present]
    jobs = []
    for item in items:
        if item.label:
            continue
        x = store.results.get((x_arm, item.id))
        for y_arm in y_arms:
            y = store.results.get((y_arm, item.id))
            if x is None or y is None or (item.id, x_arm, y_arm) in store.grades:
                continue
            jobs.append((item, x, y))

    planned = len(jobs) * len(graders) * 2
    log(f"  grading: {len(jobs)} pair(s) x {len(graders)} grader(s) x 2 orders = {planned} grader call(s)"
        + (f", comparing {x_arm} against {', '.join(y_arms)}" if y_arms else ""))
    if dry_run:
        log("  (dry run: nothing sent)")
        return errors

    spent = [0.0]
    # Every pair fires graders x 2 orders at once, so an unbounded gather over 12 pairs meant 24 simultaneous requests
    # and every one of them rate-limited. Pairs now go through a semaphore.
    sem = asyncio.Semaphore(max(1, concurrency))

    async def one(item: Item, x: ArmResult, y: ArmResult) -> None:
        async with sem:
            g = await grade_pair(client, graders, item.id, item.text, x.arm, x.text, y.arm, y.text,
                                 **({"max_tokens": max_tokens} if max_tokens else {}))
        spent[0] += g.cost
        if g.error:
            errors.append(f"grading {item.id} {x.arm} vs {y.arm}: {g.error}")
            return
        store.add_grade(g)
        partial = f"  [{g.failures} of {len(graders) * 2} calls failed: {g.error_detail}]" if g.failures else ""
        log(f"  graded {item.id:10s} {x.arm} vs {y.arm}: overall {g.outcome['overall']}  (${spent[0]:.4f} so far){partial}")

    await asyncio.gather(*[one(*j) for j in jobs])
    if jobs:
        log(f"  grading cost ${spent[0]:.4f} over {planned} call(s)")
    return errors
