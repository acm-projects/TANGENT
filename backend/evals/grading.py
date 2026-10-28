"""Blind pairwise grading of open-ended answers.

Two answers to the same question are shown to a grader model as "Answer 1" and "Answer 2", with no hint which arm wrote
which. Each grader sees the pair in BOTH orders, so a bias toward whichever answer comes first cancels out, and the
report says how often a grader contradicted itself when the order was swapped (a measure of how much to trust it).

Use graders from a different model family than the answers they judge: models tend to prefer their own style. The debate's
own judge (GPT-6 Luna) writes the debate's final text, and the debaters are Haiku, so pick graders that are neither.

What a grader cannot be blinded to is format: a debate answer usually has a verdict line and a "would change if" list. The
prompt tells graders to ignore format and length, and the report shows average length so you can see if that failed.
"""
from __future__ import annotations

import asyncio
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Optional

from debate.openrouter import lenient_loads

CRITERIA = ("accuracy", "balance", "calibration", "usefulness", "overall")

GRADER_PROMPT = """You are grading two answers to the same question. You do not know who or what wrote them.

Question:
{question}

<answer_1>
{a}
</answer_1>

<answer_2>
{b}
</answer_2>

Judge on these, one at a time. Ignore length, formatting, headings and tone; a longer answer is not a better one.
- accuracy: are the factual claims correct and properly supported? Penalise invented facts, invented sources and claims that go beyond what a source shows.
- balance: does it deal fairly with the strongest considerations on the other side, instead of only the side it prefers?
- calibration: does it say how sure it is, where the evidence is thin, and what would change its answer, without hedging everything?
- usefulness: would a thoughtful reader be better placed to decide or act after reading it?
- overall: which answer would you rather be given?

Reply with JSON only, no other text:
{{"accuracy": "1|2|tie", "balance": "1|2|tie", "calibration": "1|2|tie", "usefulness": "1|2|tie", "overall": "1|2|tie", "reason": "one sentence"}}"""


@dataclass
class PairGrade:
    question_id: str
    x_arm: str
    y_arm: str
    # per criterion: "x" | "y" | "tie", decided by majority over all (grader, order) votes
    outcome: dict[str, str] = field(default_factory=dict)
    votes: dict[str, dict[str, int]] = field(default_factory=dict)
    self_consistent: dict[str, Optional[bool]] = field(default_factory=dict)  # per grader: same overall pick in both orders?
    cost: float = 0.0
    failures: int = 0  # grader calls that produced nothing, out of graders x 2 orders
    error_detail: str = ""  # why those failed, when the pair is still usable
    error: Optional[str] = None


def _pick(d: dict[str, Any], key: str) -> str:
    v = str(d.get(key, "tie")).strip().lower()
    return "1" if v.startswith("1") else "2" if v.startswith("2") else "tie"


GRADER_MAX_TOKENS = 3000  # the JSON is tiny, but a grader that reasons first spends most of its budget before writing it
GRADER_MAX_TOKENS_CAP = 12000


async def _one(client: Any, model: str, question: str, a: str, b: str,
               max_tokens: int = GRADER_MAX_TOKENS, tries: int = 3) -> tuple[Optional[dict[str, Any]], float, str]:
    """One grader call -> (parsed, cost, error).

    A failure must not sink the comparison, but it must be *reported*: swallowing the reason once turned 24 failed calls
    into a silent "no grader reply could be read", and the real cause (replies cut off at the token limit) stayed hidden
    for a whole run. Reasoning tokens count against max_tokens, so a model that thinks before answering can spend the
    whole budget and return nothing; that is retried with a bigger one, the way the debate's own calls are.
    """
    msg = [{"role": "user", "content": GRADER_PROMPT.format(question=question.strip(), a=a.strip(), b=b.strip())}]
    cost = 0.0
    budget = max_tokens
    last = "no reply"
    for _ in range(max(1, tries)):
        try:
            res = await client.chat(model=model, max_tokens=budget, messages=msg)
        except Exception as e:
            return None, cost, f"{model}: call failed: {type(e).__name__}: {str(e)[:200]}"
        cost += res.usage.cost
        raw = (res.message.get("content") or "").strip()
        if raw:
            try:
                return lenient_loads(raw), cost, ""
            except ValueError:
                return None, cost, f"{model}: reply was not JSON: {raw[:160]!r}"
        last = (f"{model}: empty reply (finish_reason={res.finish_reason or '?'}, "
                f"reasoning_tokens={res.usage.reasoning_tokens}, max_tokens={budget})")
        if res.finish_reason != "length" or budget >= GRADER_MAX_TOKENS_CAP:
            break
        budget = min(budget * 2, GRADER_MAX_TOKENS_CAP)
    return None, cost, last


async def grade_pair(client: Any, graders: list[str], question_id: str, question: str, x_arm: str, x_text: str,
                     y_arm: str, y_text: str, max_tokens: int = GRADER_MAX_TOKENS) -> PairGrade:
    jobs = []
    for g in graders:
        jobs.append((g, "xy", _one(client, g, question, x_text, y_text, max_tokens)))
        jobs.append((g, "yx", _one(client, g, question, y_text, x_text, max_tokens)))
    done = await asyncio.gather(*[j[2] for j in jobs])
    votes: dict[str, Counter] = {c: Counter() for c in CRITERIA}
    overall_by_grader: dict[str, dict[str, str]] = {g: {} for g in graders}
    cost = 0.0
    counted = 0
    why: list[str] = []
    for (g, order, _), (d, c, err) in zip(jobs, done):
        cost += c
        if d is None:
            if err and err not in why:
                why.append(err)
            continue
        counted += 1
        for crit in CRITERIA:
            p = _pick(d, crit)
            who = "tie" if p == "tie" else (("x" if p == "1" else "y") if order == "xy" else ("y" if p == "1" else "x"))
            votes[crit][who] += 1
            if crit == "overall":
                overall_by_grader[g][order] = who
    pg = PairGrade(question_id=question_id, x_arm=x_arm, y_arm=y_arm, cost=cost)
    pg.failures = len(jobs) - counted
    if not counted:
        pg.error = "; ".join(why) or "no grader reply could be read"
        return pg
    pg.error_detail = "; ".join(why)  # some calls failed but the pair is still usable
    for crit in CRITERIA:
        v = votes[crit]
        pg.votes[crit] = {k: v.get(k, 0) for k in ("x", "y", "tie")}
        pg.outcome[crit] = "x" if v["x"] > v["y"] else "y" if v["y"] > v["x"] else "tie"
    for g, o in overall_by_grader.items():
        pg.self_consistent[g] = (o["xy"] == o["yx"]) if len(o) == 2 else None
    return pg


def summarize_grades(grades: list[PairGrade], x_arm: str, y_arm: str) -> dict[str, Any]:
    """Per criterion: how often x beat y, y beat x, or they tied, plus self-consistency of the graders."""
    from .stats import win_rate

    mine = [g for g in grades if g.x_arm == x_arm and g.y_arm == y_arm and not g.error]
    out: dict[str, Any] = {"pairs": len(mine), "criteria": {}}
    for crit in CRITERIA:
        w = sum(1 for g in mine if g.outcome.get(crit) == "x")
        l = sum(1 for g in mine if g.outcome.get(crit) == "y")
        t = len(mine) - w - l
        out["criteria"][crit] = win_rate(w, l, t)
    flags = [v for g in mine for v in g.self_consistent.values() if v is not None]
    out["self_consistency"] = (sum(flags) / len(flags)) if flags else None
    return out
