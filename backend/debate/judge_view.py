from __future__ import annotations

from typing import Any

from .deps import JudgeView
from .schemas import Evidence


def build_judge_view(state: dict[str, Any], label_of: dict[str, str]) -> JudgeView:
    turns = [t for t in state.get("turns", []) if t["phase"] != "research"]
    pool = state.get("evidence_pool", {})

    idmap: dict[str, str] = {}
    counters = {"A": 0, "B": 0}
    claims: dict[str, dict] = {}
    cite_stats: dict[str, dict[str, int]] = {"A": {"total": 0, "unverified": 0}, "B": {"total": 0, "unverified": 0}}
    for t in turns:
        lab = label_of[t["side"]]
        for c in t["claims"]:
            if c["id"] not in idmap:
                counters[lab] += 1
                idmap[c["id"]] = f"{lab}{counters[lab]}"
                claims[idmap[c["id"]]] = {"label": lab, "cited": bool(c["evidence_ids"])}
                for eid in c["evidence_ids"]:
                    cite_stats[lab]["total"] += 1
                    if eid not in pool:
                        cite_stats[lab]["unverified"] += 1

    lines = [
        f"Proposition: {state.get('proposition', '')}",
        "",
        "<project_context>",
        state.get("context_text") or "(none)",
        "</project_context>",
        "",
    ]
    answered = [q for q in state.get("user_context", []) if q.get("answer") is not None]
    if answered:
        lines.append("<user_clarifications>")
        lines += [f"- {q['prompt']} -> {q['answer']}" for q in answered]
        lines.append("</user_clarifications>")
        lines.append("")
    lines.append("Debate transcript:")

    cited: dict[str, Evidence] = {}
    for t in turns:
        lab = label_of[t["side"]]
        title = t["phase"] + (f" {t['round']}" if t["phase"] == "rebuttal" else "")
        lines.append(f"[Position {lab} | {title}]")
        lines.append(t["argument"])
        for c in t["claims"]:
            ev = ", ".join(c["evidence_ids"]) or "none"
            lines.append(f"  {idmap[c['id']]}: {c['text']} (evidence: {ev})")
            for eid in c["evidence_ids"]:
                if eid in pool:
                    cited[eid] = Evidence(**pool[eid])
        if t.get("truncated"):
            lines.append("  (turn was cut short)")

    # The judge can only check a citation if it can read what was cited. Before this, it saw ids and nothing else.
    if cited:
        lines.append("")
        lines.append("<cited_evidence>")
        for eid, ev in sorted(cited.items()):
            lines.append(f"[{eid}] {ev.title}" + (f" ({ev.year})" if ev.year else "") + (f": {ev.snippet}" if ev.snippet else ""))
        lines.append("</cited_evidence>")
        lines.append("")

    report = state.get("citation_report", {})
    for side, bad in report.items():
        if bad:
            lines.append(f"Unverified citation ids in Position {label_of[side]}: {', '.join(sorted(set(bad)))}")

    return JudgeView(rendered="\n".join(lines), labels=sorted(label_of.values()), cited_evidence=cited, claims=claims, cite_stats=cite_stats)
