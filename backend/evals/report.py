"""Turns results.jsonl and grades.jsonl into numbers a person can read."""
from __future__ import annotations

from typing import Any

from .arms import ArmResult, words
from .datasets import Item
from .grading import CRITERIA, summarize_grades
from .stats import brier, sign_test, wilson
from .runner import Store

ORDER = ["single", "cot", "vote", "rag", "selfdebate", "selfdebate_rag", "debate"]


def _arms(store: Store) -> list[str]:
    present = {a for (a, _i) in store.results}
    return [a for a in ORDER if a in present] + sorted(present - set(ORDER))


def claims_table(items: list[Item], store: Store) -> dict[str, Any]:
    claims = {i.id: i for i in items if i.label}
    arms = _arms(store)
    rows: dict[str, Any] = {}
    for arm in arms:
        all_rs = [store.results[(arm, cid)] for cid in claims if (arm, cid) in store.results]
        # A call that came back empty or errored is an infrastructure failure, not the arm answering wrongly, so it is
        # counted separately and left out of accuracy. Decided before any real run, so it cannot be tuned to a result.
        rs = [r for r in all_rs if not r.error]
        failed = len(all_rs) - len(rs)
        if not rs:
            if failed:
                rows[arm] = {"n": 0, "failed": failed, "correct": 0, "accuracy": None, "ci": (0.0, 0.0), "answered": None,
                             "accuracy_when_answered": None, "brier": None, "n_conf70": 0, "acc_conf70": None,
                             "cost": sum(r.cost for r in all_rs) / len(all_rs), "seconds": sum(r.seconds for r in all_rs) / len(all_rs),
                             "cites_verified": 0.0}
            continue
        right = [r for r in rs if r.label == claims[r.item_id].label]
        answered = [r for r in rs if r.label in ("true", "false")]
        right_answered = [r for r in answered if r.label == claims[r.item_id].label]
        conf_pairs = [(r.confidence, r.label == claims[r.item_id].label) for r in answered if r.confidence is not None]
        hi = [r for r in answered if (r.confidence or 0) >= 0.7]
        hi_right = [r for r in hi if r.label == claims[r.item_id].label]
        lo, hi_ci = wilson(len(right), len(rs))
        rows[arm] = {
            "n": len(rs), "failed": failed, "correct": len(right), "accuracy": len(right) / len(rs), "ci": (lo, hi_ci),
            "answered": len(answered) / len(rs),
            "accuracy_when_answered": (len(right_answered) / len(answered)) if answered else None,
            "brier": brier(conf_pairs), "n_conf70": len(hi), "acc_conf70": (len(hi_right) / len(hi)) if hi else None,
            "cost": sum(r.cost for r in rs) / len(rs), "seconds": sum(r.seconds for r in rs) / len(rs),
            "cites_verified": sum(r.cites_verified for r in rs) / len(rs),
            "retrieved": sum(r.retrieved_n for r in rs) / len(rs),
        }
    # For a claim the proposition is "the evidence supports the claim", so a debate that reaches no clear winner has found
    # the claim unestablished. Whether that counts as "false" is a judgement call, so BOTH readings are always reported and
    # neither can be chosen after the fact. The strict reading (no clear winner = wrong) stays the headline number.
    alt = None
    debate_rs = [store.results[(cid)] for cid in [("debate", c) for c in claims] if cid in store.results]
    debate_rs = [r for r in debate_rs if not r.error]
    if debate_rs:
        hits = sum(1 for r in debate_rs
                   if (r.label if r.label in ("true", "false") else "false") == claims[r.item_id].label)
        lo, hi_ci = wilson(hits, len(debate_rs))
        alt = {"n": len(debate_rs), "correct": hits, "accuracy": hits / len(debate_rs), "ci": (lo, hi_ci)}

    paired: dict[str, Any] = {}
    if "debate" in rows:
        for arm in rows:
            if arm == "debate":
                continue
            ids = [c for c in claims if ("debate", c) in store.results and (arm, c) in store.results
                   and not store.results[("debate", c)].error and not store.results[(arm, c)].error]
            only_d = sum(1 for c in ids if store.results[("debate", c)].label == claims[c].label != store.results[(arm, c)].label)
            only_o = sum(1 for c in ids if store.results[(arm, c)].label == claims[c].label != store.results[("debate", c)].label)
            paired[arm] = {"n": len(ids), "only_debate_right": only_d, "only_other_right": only_o, "p": sign_test(only_d, only_o)}
    return {"rows": rows, "paired": paired, "debate_no_winner_as_false": alt}


def side_bias(items: list[Item], store: Store) -> Optional[dict[str, Any]]:
    """Does the judge favour one side regardless of the answer?

    For every debate this compares the FOR and AGAINST totals and counts which side led. A side that leads nearly every
    debate is a property of the scoring, not of the questions, and it shows up here long before accuracy differences do
    (a consistent direction needs far fewer questions to detect than a small accuracy gap).
    """
    rows = [store.results[(a, i)] for (a, i) in store.results if a == "debate"]
    pairs = []
    for r in rows:
        tot = (r.extra or {}).get("totals") or {}
        if isinstance(tot.get("for"), (int, float)) and isinstance(tot.get("against"), (int, float)):
            pairs.append((float(tot["for"]), float(tot["against"])))
    if not pairs:
        return None
    n = len(pairs)
    for_led = sum(1 for f, a in pairs if f > a)
    against_led = sum(1 for f, a in pairs if a > f)
    answers = {k: 0 for k in ("true", "false", "unsure")}
    for r in rows:
        if r.label in answers:
            answers[r.label] += 1
        elif not r.error:
            answers["unsure"] += 1
    truth = {"true": 0, "false": 0}
    for item in items:
        if item.label in truth:
            truth[item.label] += 1
    checked = [r for r in rows if (r.extra or {}).get("prose_matches_winner") is not None]
    contradicted = [r for r in checked if r.extra.get("prose_contradicts_winner") is True]
    uncommitted = [r for r in checked
                   if r.extra.get("prose_contradicts_winner") is not True and r.extra["prose_matches_winner"] is False]
    return {
        "n": n,
        "prose_checked": len(checked), "prose_contradicted": len(contradicted), "prose_uncommitted": len(uncommitted),
        "for_mean": round(sum(f for f, _ in pairs) / n, 2),
        "against_mean": round(sum(a for _, a in pairs) / n, 2),
        "advantage_to_against": round(sum(a - f for f, a in pairs) / n, 2),
        "for_led": for_led, "against_led": against_led,
        "p": sign_test(for_led, against_led),
        "answers": answers, "truth": truth,
    }


def topics_table(items: list[Item], store: Store) -> dict[str, Any]:
    ids = [i.id for i in items if not i.label]
    arms = _arms(store)
    stats = {}
    for arm in arms:
        rs = [store.results[(arm, t)] for t in ids if (arm, t) in store.results]
        if rs:
            stats[arm] = {"n": len(rs), "words": sum(words(r.text) for r in rs) / len(rs), "cost": sum(r.cost for r in rs) / len(rs),
                          "seconds": sum(r.seconds for r in rs) / len(rs), "cites_verified": sum(r.cites_verified for r in rs) / len(rs),
                          "cites_total": sum(r.cites_total for r in rs) / len(rs)}
    grades = list(store.grades.values())
    vs = {}
    for (q, x, y) in {(g.question_id, g.x_arm, g.y_arm) for g in grades}:
        vs.setdefault((x, y), None)
    for (x, y) in vs:
        vs[(x, y)] = summarize_grades(grades, x, y)
    return {"arms": stats, "vs": vs}


def _pct(x: Any) -> str:
    return "n/a" if x is None else f"{100 * x:.0f}%"


def render(items: list[Item], store: Store, errors: list[str] | None = None) -> str:
    out = ["# Debate vs single call", ""]
    c = claims_table(items, store)
    if c["rows"]:
        out += ["## Claims with a known answer (accuracy, no judge involved)", "",
                "| arm | n | failed | accuracy | 95% CI | answered | acc. when answered | Brier | acc. at conf ≥70% | papers retrieved | cites verified | $/question | s/question |",
                "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for arm, r in c["rows"].items():
            b = "n/a" if r["brier"] is None else f"{r['brier']:.3f}"
            hi = "n/a" if r["acc_conf70"] is None else f"{_pct(r['acc_conf70'])} (n={r['n_conf70']})"
            out.append(f"| {arm} | {r['n']} | {r.get('failed', 0)} | **{_pct(r['accuracy'])}** | {_pct(r['ci'][0])}–{_pct(r['ci'][1])} | {_pct(r['answered'])} | "
                       f"{_pct(r['accuracy_when_answered'])} | {b} | {hi} | {r.get('retrieved', 0):.1f} | {r['cites_verified']:.1f} | {r['cost']:.4f} | {r['seconds']:.0f} |")
        out += ["", "'Papers retrieved' is what the arm was given to read; 'cites verified' is how many of its citations exist in that set. "
                "An arm with 0 retrieved cites from memory, so nothing it names can be checked.",
                "", "Accuracy counts 'unsure' and 'no clear winner' as wrong. 'Acc. when answered' leaves them out. Brier: lower is better, 0.25 is a coin flip.",
                "'failed' counts calls that came back empty or errored after retries; those are left out of every other number in the row.", ""]
        if c.get("debate_no_winner_as_false"):
            a = c["debate_no_winner_as_false"]
            out += [f"Reading a debate's 'no clear winner' as 'the claim is not established' instead of as an abstention gives the debate "
                    f"**{_pct(a['accuracy'])}** ({a['correct']}/{a['n']}, CI {_pct(a['ci'][0])}–{_pct(a['ci'][1])}). "
                    "Both readings are reported so neither can be picked after seeing the data; the strict one above is the headline.", ""]
        if c["paired"]:
            out += ["Paired against the debate (same claims; 'only X right' counts claims where exactly one of the two was right):", "",
                    "| vs | n | only debate right | only other right | p (sign test) |", "|---|---|---|---|---|"]
            for arm, p in c["paired"].items():
                out.append(f"| {arm} | {p['n']} | {p['only_debate_right']} | {p['only_other_right']} | {p['p']:.3f} |")
            out.append("")
    sb = side_bias(items, store)
    if sb:
        out += ["## Side bias in the judge (does one side win regardless of the answer?)", "",
                f"Over {sb['n']} debates the judge's totals averaged **FOR {sb['for_mean']}** and **AGAINST {sb['against_mean']}**, "
                f"an average advantage of **{sb['advantage_to_against']}** to AGAINST. FOR led {sb['for_led']} debates, AGAINST led {sb['against_led']} "
                f"(sign test p = {sb['p']:.3f}).", ""]
        if sb["truth"]["true"] or sb["truth"]["false"]:
            a, tr = sb["answers"], sb["truth"]
            out += [f"The debate answered true {a['true']}, false {a['false']}, unsure {a['unsure']} — against a set that is "
                    f"{tr['true']} true and {tr['false']} false. Always answering the more common label would score "
                    f"{max(tr.values())}/{sum(tr.values())}.", ""]
        if sb.get("prose_checked"):
            out += [f"The written verdict was read independently and compared with the scored winner in {sb['prose_checked']} debates. "
                    f"It argued for the **opposite** side in {sb['prose_contradicted']} (reported as no clear winner, because two "
                    f"readings naming different sides is not a verdict) and reached no conclusion of its own in "
                    f"{sb['prose_uncommitted']} (left as scored: the judge supplies the analysis, the rubric resolves it).", ""]
        out += ["One side leading nearly every debate is a property of the scoring rather than of the questions. The negation test "
                "(`--negate`) checks it directly: it flips each claim so the correct answer becomes FOR, and if AGAINST still leads, "
                "the rubric is the cause.", ""]
    t = topics_table(items, store)
    if t["arms"]:
        out += ["## Open questions (blind pairwise grading)", "",
                "| arm | n | words | cites (verified/total) | $/question | s/question |", "|---|---|---|---|---|---|"]
        for arm, r in t["arms"].items():
            out.append(f"| {arm} | {r['n']} | {r['words']:.0f} | {r['cites_verified']:.1f}/{r['cites_total']:.1f} | {r['cost']:.4f} | {r['seconds']:.0f} |")
        out.append("")
        for (x, y), s in t["vs"].items():
            if not s["pairs"]:
                continue
            out += [f"**{x} vs {y}** ({s['pairs']} questions, each judged in both orders by every grader; grader self-consistency {_pct(s['self_consistency'])})", "",
                    f"| criterion | {x} wins | {y} wins | ties | {x} win rate | p |", "|---|---|---|---|---|---|"]
            for crit in CRITERIA:
                w = s["criteria"][crit]
                out.append(f"| {crit} | {w['wins']} | {w['losses']} | {w['ties']} | {_pct(w['rate'])} | {w['p']:.3f} |")
            out.append("")
    if errors:
        out += ["## Errors (these items are not in the numbers above)", ""] + [f"- {e}" for e in errors] + [""]
    return "\n".join(out)
