"""What the new debate node shows: a title that says who won, and chats the user can keep talking in.

Chats are two messages (user "Debate: ...", assistant verdict card). The assistant reply is plain markdown, written
so a follow-up chat on this node has the full outcome as context.
"""
from __future__ import annotations

import datetime as _dt
from typing import Any, Optional

SIDE = {"for": "FOR", "against": "AGAINST"}


def node_title(payload: dict[str, Any], topic: str) -> str:
    prop = (payload.get("proposition") or topic).strip()
    w, reason = payload["winner"], payload.get("end_reason")
    if reason == "user_picked":
        head = f"{SIDE.get(w, 'No winner')} (your pick)"
    elif reason == "user_stopped":
        head = "Stopped early" if w == "no_clear_winner" else f"{SIDE[w]} (stopped early)"
    elif w == "no_clear_winner":
        head = "No clear winner"
    else:
        head = f"{SIDE[w]} wins"
    room = max(10, 60 - len(head) - 3)
    short = prop if len(prop) <= room else prop[: room - 1].rstrip() + "…"
    return f"{head}: {short}"


def _headline(payload: dict[str, Any]) -> str:
    w, reason = payload["winner"], payload.get("end_reason")
    would = payload.get("judge_would_have_chosen")
    if reason == "user_picked":
        line = f"**You chose {SIDE[w]}.**"
        if would and would != w:
            line += f" On the merits the judge would have picked {SIDE.get(would, 'neither side')}."
        elif would == w:
            line += " The judge agreed."
        return line
    if reason == "user_stopped":
        base = "**You ended the debate early.** "
        return base + ("The judge saw no clear winner from what was argued." if w == "no_clear_winner" else f"From what was argued the judge leaned {SIDE[w]}.")
    if w == "no_clear_winner":
        return "**Verdict: no clear winner.**"
    conf = payload.get("confidence")
    return f"**Verdict: {SIDE[w]}**" + (f" (confidence {conf:.0%})" if isinstance(conf, (int, float)) and conf else "")


def _scoring_block(rub: dict[str, Any]) -> str:
    """How the verdict was reached, so it can be checked: three model-scored criteria plus the evidence score from the claim labels."""
    lines = ["**How it was scored** (0 to 10; evidence 40%, scope 25%, engagement 25%, fidelity 10%)"]
    for side in ("for", "against"):
        c = (rub.get("criteria") or {}).get(side) or {}
        n = (rub.get("claim_counts") or {}).get(side) or {}
        total = (rub.get("totals") or {}).get(side)
        if not c:
            continue
        lines.append(
            f"- {SIDE[side]}: **{total}**. Evidence {c.get('evidence', 0):.1f} "
            f"({n.get('supported', 0)} supported, {n.get('partly_supported', 0)} partly, {n.get('unsupported', 0)} unsupported, {n.get('uncited', 0)} uncited claims), "
            f"scope {c.get('scope', 0):.0f}, engagement {c.get('engagement', 0):.0f}, fidelity {c.get('fidelity', 0):.0f}"
        )
    lines.append(f"A winner needs a lead of at least {rub.get('margin', 1.0)}; the lead here was {rub.get('gap')}.")
    return "\n".join(lines)


def render_chats(topic: str, payload: dict[str, Any], models: Optional[dict[str, str]] = None, now: Optional[str] = None) -> list[dict[str, Any]]:
    prop = payload.get("proposition") or topic
    parts = [_headline(payload), payload["summary"], payload["final_output"]]
    rub = (payload.get("scores") or {}).get("rubric")
    if rub:
        parts.append(_scoring_block(rub))
    cp = payload.get("strongest_counterpoints") or []
    if cp:
        parts.append("**Strongest points against this conclusion**\n" + "\n".join(f"- {x}" for x in cp))
    fl = payload.get("verdict_flips_if") or []
    if fl:
        parts.append("**This would change if**\n" + "\n".join(f"- {x}" for x in fl))
    cites = payload.get("citations") or []
    if cites:
        rows = []
        for c in cites:
            y = f" ({c['year']})" if c.get("year") else ""
            u, t = c.get("url"), c.get("title") or c.get("id") or "paper"
            rows.append(f"- [{t}]({u}){y}" if u else f"- {t}{y}")
        parts.append("**Papers cited**\n" + "\n".join(rows))
    if models:
        m = models
        parts.append(
            "*Debaters: " + (f"{m['for']} (both sides)" if m["for"] == m["against"] else f"FOR {m['for']}, AGAINST {m['against']}")
            + f". Judge: {m['judge']}.*"
        )
    now = now or _dt.datetime.now(_dt.timezone.utc).isoformat()
    return [
        {"role": "user", "content": f"Debate: {prop}", "seq": 0, "branch_source": None, "created_at": now},
        {"role": "assistant", "content": "\n\n".join(p for p in parts if p), "seq": 1, "branch_source": None, "created_at": now},
    ]