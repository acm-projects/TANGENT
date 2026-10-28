"""The things being compared. Every arm takes one Item and returns one ArmResult.

single   one plain model call, the way a person would ask. For a claim it is asked to end with a VERDICT line.
cot      the same single call with the model's reasoning effort turned up ("think step by step", done properly).
rag      two calls: the model writes search queries, we run them on Semantic Scholar, the model answers from the papers.
         This is the honest control for "is it the debate, or just the search?".
vote     k independent single calls, majority vote (claims only). The control for "is it just more compute?".
debate   the real debate graph, run in-process (no database): both debaters, search, rebuttals, the multi-sample judge.

Each result records cost and time, so the report can show what a point of quality costs.
"""
from __future__ import annotations

import asyncio
import random
import re
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Awaitable, Callable, Optional

from debate.deps import Deps
from debate.fakes import InMemoryControl, InMemoryEmitter, InMemoryWriter
from debate.graph import build_graph
from debate.openrouter import lenient_loads
from debate.runner import build_resume, merge_pending, run_segment
from langgraph.checkpoint.memory import InMemorySaver

from .datasets import Item

NEUTRAL_ANSWER = "No preference: use your best judgement."
CITE = re.compile(r"s2-[0-9a-f]{6,}")
MAX_TOKENS_CAP = 16000  # a reply cut off at the limit is retried with double the budget, up to this
EMPTY_REPLY = "the model returned no text"


async def ask(client: Any, model: str, prompt: str, *, max_tokens: int = 3000, tries: int = 3) -> tuple[str, float, int, str]:
    """One prompt, one answer: (text, cost, calls, error).

    Reasoning tokens count against max_tokens, so a model asked to think hard can spend the whole budget before writing
    anything and come back empty with finish_reason='length'. The debate's own calls retry that with a bigger budget
    (openrouter._structured); these arms must too, or an infrastructure failure is silently scored as a wrong answer.
    """
    cost = 0.0
    calls = 0
    budget = max_tokens
    last = EMPTY_REPLY
    for _ in range(max(1, tries)):
        res = await client.chat(model=model, messages=[{"role": "user", "content": prompt}], max_tokens=budget)
        cost += res.usage.cost
        calls += 1
        text = (res.message.get("content") or "").strip()
        if text:
            return text, cost, calls, ""
        last = f"{EMPTY_REPLY} (finish_reason={res.finish_reason or '?'}, reasoning_tokens={res.usage.reasoning_tokens})"
        if budget >= MAX_TOKENS_CAP:
            break
        budget = min(budget * 2, MAX_TOKENS_CAP)
    return "", cost, calls, last


@dataclass
class ArmResult:
    arm: str
    item_id: str
    text: str
    label: Optional[str] = None  # claims: "true" | "false" | "unsure"
    confidence: Optional[float] = None  # 0..1, the arm's own stated confidence in its label
    cost: float = 0.0
    seconds: float = 0.0
    calls: int = 0
    cites_total: int = 0  # source ids the answer cites
    cites_verified: int = 0  # ...that exist in the evidence the arm actually retrieved
    retrieved: list[dict[str, Any]] = field(default_factory=list)  # [{id, title, year}] the arm was given to read
    retrieved_n: int = 0  # len(retrieved) before the cap below, so a truncated list still reports the real total
    error: Optional[str] = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ArmResult":
        return cls(**d)


# ------------------------------------------------------------------ prompts
CLAIM_SUFFIX = (
    "\n\nExplain briefly, then finish with these two lines exactly:\n"
    "VERDICT: TRUE or FALSE or UNSURE\n"
    "CONFIDENCE: a number from 0 to 100 (how likely your verdict is correct)"
)


def claim_prompt(claim: str) -> str:
    return f"Is the following claim true, according to the scientific evidence?\n\nClaim: {claim}" + CLAIM_SUFFIX


def prompt_for(item: Item, target_words: Optional[int] = None) -> str:
    if item.label:
        base = claim_prompt(item.text)
    else:
        base = item.text
    if target_words:
        base += f"\n\n(Answer in about {target_words} words.)"
    return base


def parse_verdict(text: str) -> tuple[str, Optional[float]]:
    """('true'|'false'|'unsure', confidence 0..1 or None) from the last VERDICT / CONFIDENCE lines. Unparseable is 'unsure'."""
    v = re.findall(r"VERDICT\s*[:\-]\s*\**\s*(TRUE|FALSE|UNSURE)", text, re.I)
    c = re.findall(r"CONFIDENCE\s*[:\-]\s*\**\s*(\d{1,3}(?:\.\d+)?)", text, re.I)
    label = v[-1].lower() if v else "unsure"
    conf = min(1.0, float(c[-1]) / 100.0) if c else None
    return label, conf


def words(text: str) -> int:
    return len(text.split())


RETRIEVED_CAP = 40  # keep result rows readable; retrieved_n always carries the true count


def pool_rows(pool: Any) -> list[dict[str, Any]]:
    """Evidence objects or dicts -> plain rows for the result file. What an arm *retrieved* is the only way to tell a
    retrieval failure ("the right paper never came back") from a reasoning failure, and citations alone cannot show it."""
    rows: list[dict[str, Any]] = []
    for ev in (pool.values() if isinstance(pool, dict) else pool):
        d = ev if isinstance(ev, dict) else getattr(ev, "model_dump", lambda: {})()
        rows.append({"id": str(d.get("id", "")), "title": str(d.get("title", "")), "year": d.get("year")})
    return rows


# ------------------------------------------------------------------ the arms
class SingleArm:
    def __init__(self, client: Any, model: str, *, name: str = "single", max_tokens: int = 3000) -> None:
        self.client, self.model, self.name, self.max_tokens = client, model, name, max_tokens

    async def run(self, item: Item, *, target_words: Optional[int] = None) -> ArmResult:
        t0 = time.monotonic()
        text, cost, calls, err = await ask(self.client, self.model, prompt_for(item, target_words), max_tokens=self.max_tokens)
        out = ArmResult(arm=self.name, item_id=item.id, text=text, cost=cost, calls=calls, seconds=time.monotonic() - t0, error=err or None)
        if item.label and text:
            out.label, out.confidence = parse_verdict(text)
        return out


class VoteArm:
    """k independent single calls; the majority verdict wins, a tie is 'unsure'. Claims only."""

    def __init__(self, client: Any, model: str, k: int = 9, max_tokens: int = 3000) -> None:
        self.single, self.k = SingleArm(client, model, name="vote", max_tokens=max_tokens), k

    async def run(self, item: Item, *, target_words: Optional[int] = None) -> ArmResult:
        if not item.label:
            raise ValueError("the vote arm only runs on claims")
        t0 = time.monotonic()
        rs = await asyncio.gather(*[self.single.run(item) for _ in range(self.k)])
        got = [r for r in rs if not r.error]
        cost, calls = sum(r.cost for r in rs), sum(r.calls for r in rs)
        if not got:
            return ArmResult(arm="vote", item_id=item.id, text="", cost=cost, calls=calls,
                             seconds=time.monotonic() - t0, error=rs[0].error or EMPTY_REPLY)
        tally = {"true": 0, "false": 0, "unsure": 0}
        for r in got:
            tally[r.label or "unsure"] += 1
        top = max(tally, key=lambda x: tally[x])
        tied = sorted(tally.values())[-1] == sorted(tally.values())[-2]
        label = "unsure" if tied else top
        return ArmResult(arm="vote", item_id=item.id, text=got[0].text, label=label, confidence=tally[top] / len(got),
                         cost=cost, calls=calls, seconds=time.monotonic() - t0,
                         extra={"tally": tally, "replies": len(got), "asked": self.k})


class RagArm:
    def __init__(self, client: Any, model: str, search: Any, *, max_queries: int = 4, max_papers: int = 12, max_tokens: int = 3000) -> None:
        self.client, self.model, self.search = client, model, search
        self.max_queries, self.max_papers, self.max_tokens = max_queries, max_papers, max_tokens

    async def run(self, item: Item, *, target_words: Optional[int] = None) -> ArmResult:
        t0 = time.monotonic()
        qtext, cost, calls, _ = await ask(self.client, self.model, (
            f"Write up to {self.max_queries} different academic search queries that would find the best evidence for answering this.\n\n"
            f"{item.text}\n\nReply with JSON only: {{\"queries\": [\"...\"]}}"), max_tokens=800)
        try:
            queries = [str(x) for x in lenient_loads(qtext)["queries"]][: self.max_queries]
        except (ValueError, KeyError, TypeError):
            queries = [item.text]
        found = await asyncio.gather(*[self._safe(x) for x in queries])
        pool: dict[str, Any] = {}
        for batch in found:
            for ev in batch:
                pool.setdefault(ev.id, ev)
        papers = list(pool.values())[: self.max_papers]
        listing = "\n".join(f"[{e.id}] {e.title}" + (f" ({e.year})" if e.year else "") + (f": {e.snippet}" if e.snippet else "") for e in papers) or "(no papers found)"
        text, acost, acalls, err = await ask(self.client, self.model, (
            f"{prompt_for(item, target_words)}\n\nYou may use these papers. Cite a paper by its id in square brackets, "
            f"for example [s2-1a2b3c4d5e6f], only when it supports what you say. Do not cite anything not listed."
            f"\n\n<papers>\n{listing}\n</papers>"), max_tokens=self.max_tokens)
        cited = CITE.findall(text)
        out = ArmResult(arm="rag", item_id=item.id, text=text, cost=cost + acost, calls=calls + acalls,
                        seconds=time.monotonic() - t0, error=err or None,
                        cites_total=len(set(cited)), cites_verified=len({c for c in cited if c in pool}),
                        retrieved=pool_rows(papers)[:RETRIEVED_CAP], retrieved_n=len(papers),
                        extra={"queries": queries, "papers": len(papers)})
        if item.label and text:
            out.label, out.confidence = parse_verdict(text)
        return out

    async def _safe(self, query: str) -> list[Any]:
        try:
            return await self.search.search(query)
        except Exception:  # a failed search must not sink the arm
            return []


class SelfDebateArm:
    """One call that is asked to do what the debate does: argue both sides, weigh them, and report its own uncertainty.

    This is the baseline that actually threatens the product. `cot` only turns reasoning effort up; this asks for the same
    *shape* of answer the debate produces. If it matches the debate under blind grading, the orchestration is buying
    verifiability rather than quality -- which is worth knowing before anyone else asks. With `search` it also gets real
    retrieved papers, which separates "arguing both sides helps" from "having sources helps".
    """

    PROMPT = (
        "Work through this as a careful researcher who argues both sides before deciding.\n\n"
        "{question}\n\n"
        "Do all of the following, in this order, under these headings:\n"
        "1. THE CASE FOR: the strongest honest case that the answer is yes (or that the claim is accurate). Give its best "
        "evidence, not a strawman.\n"
        "2. THE CASE AGAINST: the strongest honest case for the opposite. Give it the same effort.\n"
        "3. WEIGHING: where the two cases actually conflict, and which holds up better and why. Say plainly where the "
        "evidence is thin, where sources are being read beyond what they show, and what is assumption rather than finding.\n"
        "4. CONCLUSION: your answer, with the uncertainty that honestly remains.\n"
        "5. STRONGEST COUNTERPOINTS: two or three points that most threaten your conclusion, stated at full strength.\n"
        "6. THIS WOULD CHANGE IF: two or three specific findings that would change your answer.\n"
    )

    def __init__(self, client: Any, model: str, search: Any = None, *, name: str = "selfdebate",
                 max_queries: int = 4, max_papers: int = 12, max_tokens: int = 6000) -> None:
        self.client, self.model, self.search, self.name = client, model, search, name
        self.max_queries, self.max_papers, self.max_tokens = max_queries, max_papers, max_tokens

    async def run(self, item: Item, *, target_words: Optional[int] = None) -> ArmResult:
        t0 = time.monotonic()
        cost = calls = 0
        papers: list[Any] = []
        pool: dict[str, Any] = {}
        queries: list[str] = []
        if self.search is not None:
            qtext, qcost, qcalls, _ = await ask(self.client, self.model, (
                f"Write up to {self.max_queries} different academic search queries that would find the best evidence on "
                f"both sides of this.\n\n{item.text}\n\nReply with JSON only: {{\"queries\": [\"...\"]}}"), max_tokens=800)
            cost, calls = cost + qcost, calls + qcalls
            try:
                queries = [str(x) for x in lenient_loads(qtext)["queries"]][: self.max_queries]
            except (ValueError, KeyError, TypeError):
                queries = [item.text]
            for batch in await asyncio.gather(*[self._safe(q) for q in queries]):
                for ev in batch:
                    pool.setdefault(ev.id, ev)
            papers = list(pool.values())[: self.max_papers]

        prompt = self.PROMPT.format(question=prompt_for(item, target_words))
        if self.search is not None:
            listing = "\n".join(
                f"[{e.id}] {e.title}" + (f" ({e.year})" if e.year else "") + (f": {e.snippet}" if e.snippet else "")
                for e in papers) or "(no papers found)"
            prompt += ("\nUse these papers for both cases. Cite one by its id in square brackets, for example "
                       f"[s2-1a2b3c4d5e6f], only where it supports what you say. Do not cite anything not listed."
                       f"\n\n<papers>\n{listing}\n</papers>\n")
        text, acost, acalls, err = await ask(self.client, self.model, prompt, max_tokens=self.max_tokens)
        cited = CITE.findall(text)
        out = ArmResult(arm=self.name, item_id=item.id, text=text, cost=cost + acost, calls=calls + acalls,
                        seconds=time.monotonic() - t0, error=err or None,
                        cites_total=len(set(cited)), cites_verified=len({c for c in cited if c in pool}),
                        retrieved=pool_rows(papers)[:RETRIEVED_CAP], retrieved_n=len(papers),
                        extra={"queries": queries, "papers": len(papers)})
        if item.label and text:
            out.label, out.confidence = parse_verdict(text)
        return out

    async def _safe(self, query: str) -> list[Any]:
        try:
            return await self.search.search(query)
        except Exception:
            return []


# ------------------------------------------------------------------ the debate arm
def debate_topic(item: Item) -> str:
    """For a claim, state the measure and the setting so the framing step has nothing to ask the user.

    The wording matters more than it looks. An earlier version ended "...otherwise people in general", and the framing
    step duly wrote propositions like "In people generally, the evidence supports that X" -- a far higher bar than the
    labelling standard, which only asks whether the literature reports what the claim says. Every debate then came down
    to "this does not generalise", which is nearly always true of an abstract, so the AGAINST side won almost every
    time. The claim's own scope is the setting; nothing may be added to it.
    """
    if not item.label:
        return item.text
    return (f"Decide whether this claim is accurate: \"{item.text}\". "
            "Measure: whether the research literature reports what the claim says, read exactly as worded and no more. "
            "Setting: exactly the population, species, cell type, model system or conditions the claim itself names, and no wider. "
            "Do not require the finding to hold beyond that scope, in people generally, or across settings the claim does not mention. "
            "Do not require a quantified effect size, an independent replication or a clinical outcome unless the claim itself mentions one. "
            "A claim is accurate if the literature reports it as stated; it is inaccurate if the literature reports the opposite, "
            "or reports nothing that bears on it.")


def deliverable(payload: dict[str, Any]) -> str:
    """What the user reads in the node, without the scoring table or model names (those would reveal the arm to a grader)."""
    w = payload["winner"]
    head = "Verdict: no clear winner." if w == "no_clear_winner" else f"Verdict: {w.upper()}."
    parts = [head, payload["summary"], payload["final_output"]]
    if payload.get("strongest_counterpoints"):
        parts.append("Strongest points against this conclusion:\n" + "\n".join(f"- {x}" for x in payload["strongest_counterpoints"]))
    if payload.get("verdict_flips_if"):
        parts.append("This would change if:\n" + "\n".join(f"- {x}" for x in payload["verdict_flips_if"]))
    if payload.get("citations"):
        parts.append("Papers cited:\n" + "\n".join(f"- {c.get('title') or c.get('id')} ({c.get('year') or 'n.d.'})" for c in payload["citations"]))
    return "\n\n".join(p for p in parts if p)


class DebateArm:
    """Runs the real graph in this process. make_brain() must return a fresh Brain per debate."""

    def __init__(self, make_brain: Callable[[], Any], search: Any, *, rounds: int = 2, judge_samples: int = 3,
                 max_cost: Optional[float] = None, polarity_check: Optional[Callable[[str, str], Awaitable[str]]] = None,
                 seed: Optional[int] = None) -> None:
        self.make_brain, self.search, self.rounds = make_brain, search, rounds
        self.judge_samples, self.max_cost, self.polarity_check, self.seed = judge_samples, max_cost, polarity_check, seed

    async def run(self, item: Item, *, target_words: Optional[int] = None) -> ArmResult:
        t0 = time.monotonic()
        did = f"eval-{item.id}"

        async def loader(_id: str) -> tuple[str, list[str]]:
            return "", []

        deps = Deps(brain=self.make_brain(), search=self.search, control=InMemoryControl(), emitter=InMemoryEmitter(),
                    context_loader=loader, writer=InMemoryWriter(), rng=random.Random(self.seed),
                    max_cost_usd=self.max_cost, judge_samples=self.judge_samples)
        graph = build_graph(InMemorySaver())
        cfg = {"configurable": {"thread_id": did, "deps": deps}, "recursion_limit": 200}
        graph_input: Any = {"debate_id": did, "topic": debate_topic(item), "rounds": self.rounds}
        for _ in range(60):
            seg = await run_segment(graph, cfg, graph_input)
            graph_input = None
            if seg.status == "done":
                break
            if seg.status == "paused":
                qs = merge_pending(seg.interrupts)
                graph_input = build_resume(seg.interrupts, {q["id"]: NEUTRAL_ANSWER for q in qs})
        else:
            raise RuntimeError("debate did not finish")
        payload = deps.writer.results[did]
        pool = ((await graph.aget_state(cfg)).values or {}).get("evidence_pool") or {}
        u = payload["usage_summary"]["total"]
        out = ArmResult(arm="debate", item_id=item.id, text=deliverable(payload), cost=float(u.get("cost") or 0.0),
                        calls=int(u.get("calls") or 0), seconds=time.monotonic() - t0)
        rub = (payload.get("scores") or {}).get("rubric") or {}
        cites = payload.get("citations") or []
        out.cites_total = out.cites_verified = len(cites)  # the graph drops unverified ids from the node
        out.retrieved, out.retrieved_n = pool_rows(pool)[:RETRIEVED_CAP], len(pool)
        out.confidence = float(payload.get("confidence") or 0.0)
        out.extra = {"proposition": payload["proposition"], "winner": payload["winner"], "gap": rub.get("gap"),
                     "agreement": rub.get("agreement"), "judge_samples": rub.get("judge_samples"), "end_reason": payload.get("end_reason"),
                     "totals": rub.get("totals"), "prose_conclusion": rub.get("prose_conclusion"),
                     "prose_matches_winner": rub.get("prose_matches_winner"),
                     "prose_contradicts_winner": rub.get("prose_contradicts_winner"),
                     "text_matches_scores": rub.get("text_matches_scores")}
        if item.label:
            side = payload["winner"]
            flip = False
            if self.polarity_check is not None and side in ("for", "against"):
                rel = await self.polarity_check(item.text, payload["proposition"])
                out.extra["polarity"] = rel
                flip = rel == "opposite"
            if side == "no_clear_winner":
                out.label = "unsure"
            else:
                says_true = (side == "for") != flip
                out.label = "true" if says_true else "false"
        return out


def make_polarity_check(client: Any, model: str) -> Callable[[str, str], Awaitable[str]]:
    """The framing step rewrites the claim into a proposition. This asks whether FOR still means 'the claim is true'."""
    async def check(claim: str, proposition: str) -> str:
        res = await client.chat(model=model, max_tokens=300, messages=[{"role": "user", "content": (
            f"Claim: {claim}\nProposition: {proposition}\n\n"
            "If someone argues FOR the proposition, are they arguing that the claim is true? "
            "Answer with exactly one word: same (FOR means the claim is true), opposite (FOR means the claim is false), or unclear.")}])
        w = (res.message.get("content") or "").strip().lower()
        return "opposite" if w.startswith("opposite") else "same" if w.startswith("same") else "unclear"
    return check
