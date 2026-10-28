"""Deterministic quality scorecard for one finished debate. No model calls, no network: pure text and number checks.

These are HEURISTICS to compare prompt and model changes run to run, not proof of correctness. A WARN means "look at this
line of the transcript", not "this is wrong". Each metric is {group, name, status, value, detail}; status is pass, warn or info.
The hard invariants (valid winner, no empty turns, ...) live in smoke_debate.check(); nothing here changes the exit code
unless you pass --strict-quality.
"""
from __future__ import annotations

import re
from typing import Any, Iterable, Optional

SIDES = ("for", "against")
ARGUING = ("opening", "rebuttal", "closing")  # research notes are private and never judged

STOP = set(
    "about above after again against also among because been before being below between both cannot could does doing each even "
    "from further have having here however into itself just more most much must only other over same should some such than that "
    "their them then there these they this those through under until very were what when where which while whose will with would "
    "your across although another any are but can did for has her him his its may might not our out she the was who why you".split()
)

CONCEDE = [re.compile(p, re.I) for p in (
    r"\bI(?:'ll|'d| will| would| do| must| also| now| fully| readily| freely| gladly)? (?:concede|accept|grant|acknowledge|admit|agree|withdraw|yield)\b",
    r"\bI (?:cannot rebut|could not rebut|can't rebut|would not contest|do not contest|am wrong|was wrong)\b",
    r"\b(?:opponent|they|he|she)\b[^.\n]{0,40}\b(?:is|are) (?:right|correct)\b",
    r"\bfair (?:point|enough)\b", r"\bto be fair\b", r"\bfair as far as\b", r"\bconcession", r"\bI'll grant\b",
    r"\bwhere (?:the |my )?(?:opponent|I) (?:is|am|are|agree)\b", r"\bI also accept\b",
    # arguing against its own side (seen in the first v2 run's FOR opening)
    r"\bI (?:do not|don't|cannot|can't|will not|won't) (?:dispute|deny|contest)\b",
    r"\bgaps? in my (?:own )?(?:case|argument)\b", r"\bagainst my (?:side|case|position|argument)\b",
    r"\b(?:is|are) a point against (?:me|my|the proposition)\b",
)]
HEDGE = re.compile(
    r"\bit depends\b|\bdepends on\b|\bno silver bullet\b|\broughly even\b|\bmixed\b|\bnot (?:been )?established\b|\binconclusive\b"
    r"|\bhold (?:that|this) loosely\b|\bfair to say\b|\bcannot show\b|\bcan't show\b|\bnot clear\b",
    re.I,
)
NUMBER = re.compile(r"(?<![\w.-])\d[\d,]*(?:\.\d+)?%?(?![\w-])")
ID_TOKEN = re.compile(r"\b[a-z0-9]+-[a-z0-9]{6,}(?:-[a-z0-9]+)*\b", re.I)
S2_ID = re.compile(r"\bs2-[0-9a-z]{6,}\b", re.I)
QUOTE = re.compile(r"[\"“]([^\"”\n]{12,200})[\"”]")
QUOTE_SINGLE = re.compile(r"(?<![\w])['‘]([^'’\n]{12,200})['’](?![\w])")  # prompts now ask for single quotes
SKIPPED = "could not be produced"
LEAKED_CLAIM_ID = re.compile(r"\b(?:for|against)-(?:research|opening|rebuttal|closing)-\d+-\d+\b|\b[AB]\d\b")
FINAL_SECTIONS = ("what the evidence supports", "still open", "caveats", "what the other side got right", "next steps")


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z][a-z0-9'-]{3,}", text.lower())


def _content(text: str) -> set[str]:
    return {w for w in _words(text) if w not in STOP}


def _jaccard(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if a | b else 0.0


def _shingles(text: str, n: int = 4) -> set[tuple[str, ...]]:
    w = re.findall(r"[a-z0-9']+", text.lower())
    return {tuple(w[i:i + n]) for i in range(len(w) - n + 1)}


def _quote_fragments(q: str) -> list[str]:
    """An honest quote may contain an ellipsis or an editorial [bracket]; check each stretch of real quoted words on its own."""
    return [f for f in re.split(r"\[[^\]]*\]|\.\.\.|\u2026", q) if f.strip()]


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9% ]+", " ", text.lower())).strip()


def _num_key(s: str) -> str:
    return s.replace(",", "").rstrip("%")


def _m(group: str, name: str, status: str, value: Any, detail: Optional[list[str]] = None) -> dict[str, Any]:
    return {"group": group, "name": name, "status": status, "value": value, "detail": detail or []}


def _tag(t: dict[str, Any]) -> str:
    return f"{t['side'].upper()} {t['phase']} {t['round']}"


def _evidence_text(e: dict[str, Any]) -> str:
    return f"{e.get('title', '')} {e.get('snippet', '')}"


def scorecard(
    state: dict[str, Any],
    result: dict[str, Any],
    events: Iterable[dict[str, Any]] = (),
    context: str = "",
    rounds: int = 2,
) -> list[dict[str, Any]]:
    events = list(events)
    turns = [t for t in state.get("turns", [])]
    is_skipped = lambda t: SKIPPED in t["argument"][:120]  # a turn the model failed to produce: reported on its own line, kept out of the other metrics
    arg = [t for t in turns if t["phase"] in ARGUING and not is_skipped(t)]
    pool: dict[str, dict[str, Any]] = state.get("evidence_pool", {})
    out: list[dict[str, Any]] = []

    # ---------------------------------------------------------------- conduct: no concessions, no hedging
    hits: list[str] = []
    for t in arg:
        for rx in CONCEDE:
            m = rx.search(t["argument"])
            if m:
                hits.append(f"{_tag(t)}: …{t['argument'][max(0, m.start() - 30):m.end() + 40].strip()}…")
                break
    out.append(_m("Conduct", "no concessions or self-undermining in arguments", "pass" if not hits else "warn", f"{len(hits)} turn(s)", hits[:6]))

    skipped = [_tag(t) for t in turns if is_skipped(t)]
    out.append(_m("Conduct", "turns the model failed to produce (skipped)", "warn" if skipped else "pass", len(skipped), skipped))

    think_hits = sum(1 for t in arg for n in t.get("thinking") or [] if any(rx.search(n) for rx in CONCEDE))
    out.append(_m("Conduct", "concession wording in thinking notes", "pass" if not think_hits else "info", f"{think_hits} note(s)"))

    closings = {t["side"]: t for t in turns if t["phase"] == "closing" and not is_skipped(t)}
    hedges = {s: len(HEDGE.findall(closings[s]["argument"])) for s in SIDES if s in closings}
    out.append(_m("Conduct", "hedging phrases in closings", "warn" if any(v >= 3 for v in hedges.values()) else "pass", hedges))

    # ---------------------------------------------------------------- argument quality: repetition, convergence, engagement, balance
    def text_of(side: str, phase: str, rnd: Optional[int] = None) -> str:
        return " ".join(t["argument"] for t in arg if t["side"] == side and t["phase"] == phase and (rnd is None or t["round"] == rnd))

    rep = {}
    for s in SIDES:
        later = _shingles(" ".join([text_of(s, "closing")] + [t["argument"] for t in arg if t["side"] == s and t["phase"] == "rebuttal" and t["round"] > 1]))
        earlier = _shingles(" ".join([text_of(s, "opening")] + [t["argument"] for t in arg if t["side"] == s and t["phase"] == "rebuttal" and t["round"] == 1]))
        rep[s] = round(len(later & earlier) / len(later), 2) if later else 0.0
    out.append(_m("Arguments", "copying earlier turns (share of later 4-grams already used)", "warn" if any(v > 0.25 for v in rep.values()) else "pass", rep))

    both = all(text_of(s, ph) for s in SIDES for ph in ("opening", "closing"))
    open_sim = _jaccard(_content(text_of("for", "opening")), _content(text_of("against", "opening")))
    close_sim = _jaccard(_content(text_of("for", "closing")), _content(text_of("against", "closing")))
    drift = round(close_sim - open_sim, 2)
    out.append(_m("Arguments", "convergence drift (closing overlap minus opening overlap)", "info" if not both else "warn" if drift > 0.08 else "pass",
                  {"opening_overlap": round(open_sim, 2), "closing_overlap": round(close_sim, 2), "drift": drift} if both else "n/a: a side has no opening or closing",
                  ["Rising overlap means the two sides are drifting to the same position."] if both and drift > 0.08 else []))

    answered, total = 0, 0
    for t in turns:
        if t["phase"] != "rebuttal" or is_skipped(t):
            continue
        opp_side = "against" if t["side"] == "for" else "for"
        prev = [o for o in turns if o["side"] == opp_side and ((t["round"] == 1 and o["phase"] == "opening") or (o["phase"] == "rebuttal" and o["round"] == t["round"] - 1))]
        for o in prev:
            for n, c in enumerate(o["claims"], 1):
                total += 1
                hit = c["id"] in t["argument"] or re.search(rf"\bclaim\s*{n}\b", t["argument"], re.I) or any(e in t["argument"] for e in c["evidence_ids"])
                answered += 1 if hit else 0
    frac = round(answered / total, 2) if total else 1.0
    out.append(_m("Arguments", "rebuttals engage the opponent's claims (by id, 'claim N' or a paper it cited)", "warn" if total and frac < 0.5 else "pass", f"{answered}/{total}"))

    words = {s: sum(len(t["argument"].split()) for t in arg if t["side"] == s) for s in SIDES}
    ratio = round(max(words.values()) / max(1, min(words.values())), 2)
    one_sided = min(words.values()) == 0
    out.append(_m("Arguments", "length balance between sides (longer/shorter)", "info" if one_sided else "warn" if ratio > 1.6 else "pass",
                  {**words, "ratio": ratio} if not one_sided else {**words, "note": "a side produced no argument"},
                  ["A much longer side can sway a judge; the judge prompt says to ignore length."] if ratio > 1.6 and not one_sided else []))

    long_notes = [f"{_tag(t)}: {len(n)} chars" for t in turns for n in t.get("thinking") or [] if len(n) > 350]
    avg_notes = round(sum(len(t.get("thinking") or []) for t in turns) / max(1, len(turns)), 1)
    out.append(_m("Arguments", "thinking notes stay short (prompt: 1-4 short notes)", "warn" if long_notes or avg_notes > 4 else "pass",
                  {"avg_notes_per_turn": avg_notes, "over_350_chars": len(long_notes)}, long_notes[:4]))

    # ---------------------------------------------------------------- evidence use: the hallucination detectors
    cited_by = {s: {e for t in arg if t["side"] == s for c in t["claims"] for e in c["evidence_ids"]} for s in SIDES}
    all_cited = cited_by["for"] | cited_by["against"]
    thin = [s for s in SIDES if len(cited_by[s] & set(pool)) < 2]
    out.append(_m("Evidence", "papers retrieved / cited by FOR / cited by AGAINST / cited by both", "warn" if thin or len(pool) < 5 else "pass",
                  {"retrieved": len(pool), "for": len(cited_by["for"]), "against": len(cited_by["against"]), "both": len(cited_by["for"] & cited_by["against"]),
                   "never_cited": len(set(pool) - all_cited)},
                  [f"{s.upper()} cites fewer than 2 retrieved papers" for s in thin]))

    ext_parts = [_evidence_text(e) for e in pool.values()] + [context, state.get("proposition", "")]
    ext_parts += [f"{q.get('prompt', '')} {q.get('answer', '')}" for q in state.get("user_context", [])]
    ext = " ".join(ext_parts)
    ext_norm, ext_nums = _norm(ext), {_num_key(n) for n in NUMBER.findall(ext)}

    def opp_text(side: str) -> str:
        return " ".join(t["argument"] + " " + " ".join(c["text"] for c in t["claims"]) for t in turns if t["side"] != side)

    bad_nums, bad_quotes, bad_ids = [], [], []
    for t in arg:
        mine = t["argument"] + " " + " ".join(c["text"] for c in t["claims"])
        scrubbed = ID_TOKEN.sub(" ", mine)
        opp = opp_text(t["side"])
        opp_nums = {_num_key(n) for n in NUMBER.findall(opp)}
        for n in NUMBER.findall(scrubbed):
            k = _num_key(n)
            plain = len(k.replace(".", "")) >= 2 or n.endswith("%") or "." in n
            is_year = re.fullmatch(r"(?:19|20)\d\d", k) is not None
            if plain and not is_year and k not in ext_nums and k not in opp_nums:
                bad_nums.append(f"{_tag(t)}: {n}")
        for q, minwords in [(x, 3) for x in QUOTE.findall(mine)] + [(x, 4) for x in QUOTE_SINGLE.findall(mine)]:  # short single quotes are often scare-quotes
            for frag in _quote_fragments(q):
                qn = _norm(frag)
                if len(qn.split()) >= minwords and qn not in ext_norm and qn not in _norm(opp):
                    bad_quotes.append(f"{_tag(t)}: \"{q[:90]}\"")
                    break
        for i in S2_ID.findall(mine):
            if i.lower() not in {p.lower() for p in pool}:
                bad_ids.append(f"{_tag(t)}: {i}")
    out.append(_m("Evidence", "numbers not found in any source, context or opponent text", "warn" if bad_nums else "pass", f"{len(bad_nums)}", sorted(set(bad_nums))[:8]))
    out.append(_m("Evidence", "direct quotes not found in any source or opponent text", "warn" if bad_quotes else "pass", f"{len(bad_quotes)}", sorted(set(bad_quotes))[:6]))
    out.append(_m("Evidence", "paper ids written in the text that are not in the pool", "warn" if bad_ids else "pass", f"{len(bad_ids)}", sorted(set(bad_ids))[:6]))

    weak, scores = [], []
    for t in arg:
        for c in t["claims"]:
            ev = [pool[e] for e in c["evidence_ids"] if e in pool]
            claim_words = _content(c["text"])
            if not ev or len(claim_words) < 5:
                continue
            ev_words = set().union(*(_content(_evidence_text(e)) for e in ev))
            s = len(claim_words & ev_words) / len(claim_words)
            scores.append(s)
            if s < 0.2:
                weak.append(f"{_tag(t)} {c['id']}: {s:.0%} of its terms appear in the cited text")
    mean = round(sum(scores) / len(scores), 2) if scores else None
    flagged = round(len(weak) / len(scores), 2) if scores else 0.0
    out.append(_m("Evidence", "claims whose terms barely appear in the cited abstract (lexical, rough)", "warn" if flagged > 0.35 else "pass",
                  {"claims_checked": len(scores), "mean_term_overlap": mean, "flagged": len(weak)}, weak[:5]))

    # ---------------------------------------------------------------- the judge
    fo = result.get("final_output", "") or ""
    summary = result.get("summary", "") or ""
    leaks = [f"{k}: {m.group(0)}" for k in ("summary", "final_output", "rationale") for m in [LEAKED_CLAIM_ID.search(result.get(k, "") or "")] if m]
    out.append(_m("Judge", "no claim ids in summary, final_output or rationale", "warn" if leaks else "pass", f"{len(leaks)}", leaks))

    unknown_ids = sorted({i for i in S2_ID.findall(fo + " " + summary) if i not in all_cited})
    out.append(_m("Judge", "no paper ids the debaters did not cite", "warn" if unknown_ids else "pass", f"{len(unknown_ids)}", unknown_ids[:5]))

    present = [s for s in FINAL_SECTIONS if s in fo.lower()]
    early = result.get("end_reason") in ("user_stopped",) and not arg
    out.append(_m("Judge", "final_output has the researcher sections", "pass" if len(present) >= 4 or early else "warn",
                  f"{len(present)}/{len(FINAL_SECTIONS)}", [f"missing: {s}" for s in FINAL_SECTIONS if s not in present] if len(present) < 4 and not early else []))
    out.append(_m("Judge", "final_output has no stray leading/trailing whitespace", "pass" if fo == fo.strip() else "warn", "clean" if fo == fo.strip() else "needs strip"))

    sentences = len([s for s in re.split(r"(?<=[.!?])\s+", summary.strip()) if s])
    out.append(_m("Judge", "summary is 2-3 sentences", "pass" if 1 <= sentences <= 4 else "warn", sentences))

    sc = result.get("scores") or {}
    w = result.get("winner")
    if w in SIDES and all(s in sc for s in SIDES):
        try:
            ok = float(sc[w]) >= float(sc["against" if w == "for" else "for"])
        except (TypeError, ValueError):
            ok = True
        out.append(_m("Judge", "winner has the higher score", "pass" if ok else "warn", {s: sc[s] for s in SIDES}))
    rub = sc.get("rubric") if isinstance(sc, dict) else None
    if rub:
        cov = rub.get("coverage", 0)
        out.append(_m("Judge", "labelled every claim (coverage of claim checks)", "pass" if cov >= 0.8 else "warn", cov))
        out.append(_m("Judge", "rubric complete for both positions", "pass" if rub.get("complete") else "warn", rub.get("complete")))
        out.append(_m("Judge", "judge's text agrees with the rubric totals", "pass" if rub.get("text_matches_scores") else "warn", rub.get("text_matches_scores")))
    out.append(_m("Judge", "confidence / winner / would-have-chosen", "info",
                  {"winner": w, "confidence": result.get("confidence"), "would_have_chosen": result.get("judge_would_have_chosen")}))
    has_both = bool(result.get("strongest_counterpoints")) and bool(result.get("verdict_flips_if"))
    out.append(_m("Judge", "gives counterpoints and what would flip the verdict", "pass" if has_both or w == "no_clear_winner" else "warn", has_both))

    # ---------------------------------------------------------------- process, reliability, cost
    tools = {s: sum(1 for e in events if e.get("type") == "tool_called" and e.get("side") == s) for s in SIDES}
    asked = {s: sum(1 for q in state.get("user_context", []) if q.get("asked_by") == s) for s in SIDES}
    out.append(_m("Process", "searches / questions to the user, per side", "warn" if min(tools.values()) == 0 else "pass",
                  {"searches": tools, "questions": asked}, [f"{s.upper()} never searched" for s in SIDES if tools[s] == 0]))
    cut = [_tag(t) for t in turns if t.get("truncated")]
    out.append(_m("Process", "turns forced to finish by the step cap", "info" if cut else "pass", len(cut), cut))

    usage = result.get("usage_summary") or {}
    tot = usage.get("total") or {}
    nodes = (result.get("timing_summary") or {}).get("by_node", {})
    if "attempts" in tot:  # real API calls minus steps: replies that had to be retried
        repairs = max(0, int(tot.get("attempts", 0)) - int(tot.get("calls", 0)))
    else:  # older usage records without an attempts count
        expected = nodes.get("agent", {}).get("count", 0) + nodes.get("frame", {}).get("count", 0) + (1 if any(t["phase"] != "research" for t in turns) else 0)
        repairs = max(0, int(tot.get("calls", 0)) - expected) if expected else 0
    out.append(_m("Process", "extra model calls from retried replies (repair retries)", "warn" if repairs > 2 else "pass", repairs))

    prompt, cached = int(tot.get("prompt_tokens", 0)), int(tot.get("cached_tokens", 0))
    cost = float(tot.get("cost", 0) or 0)
    judge_cost = float(((usage.get("by_role") or {}).get("judge") or {}).get("cost", 0) or 0)
    phases = (result.get("timing_summary") or {}).get("phases", {})
    out.append(_m("Cost", "cost / tokens / cache share / latency", "info", {
        "cost_usd": round(cost, 4), "judge_cost_usd": round(judge_cost, 4), "prompt_tokens": prompt, "completion_tokens": int(tot.get("completion_tokens", 0)),
        "reasoning_tokens": int(tot.get("reasoning_tokens", 0)), "cached_share": round(cached / prompt, 2) if prompt else 0.0,
        "model_latency_s": round(int(tot.get("latency_ms", 0)) / 1000), "debate_phases_s": round(sum(p["seconds"] for p in phases.values()))}))
    return out


def summarize(card: list[dict[str, Any]]) -> dict[str, int]:
    return {s: sum(1 for m in card if m["status"] == s) for s in ("pass", "warn", "info")}


def render(card: list[dict[str, Any]]) -> str:
    lines, group = [], None
    for m in card:
        if m["group"] != group:
            group = m["group"]
            lines.append(f"\n  [{group}]")
        lines.append(f"  {m['status'].upper():5} {m['name']}: {m['value']}")
        lines += [f"          - {d}" for d in m["detail"]]
    c = summarize(card)
    lines.append(f"\n  {c['pass']} pass, {c['warn']} warn, {c['info']} info")
    return "\n".join(lines)
