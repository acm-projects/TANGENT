"""One row per question per arm, with time, cost, answer and score, in files you can open in a spreadsheet.

comparison.csv     the numbers (no answer text), one row per (question, arm)
comparison.json    the same rows plus the full answer text
side_by_side.md    each question with every arm's answer under it, for reading

Score means: for a claim, whether the label matched the known answer; for an open question, how the blind graders ranked this
arm against each other arm (`overall_vs_<arm>`: won, lost or tie, from this row's point of view). The debate rows also carry
the judge's totals for FOR and AGAINST, the winner and confidence, and how many judge runs agreed.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from .arms import words
from .datasets import Item
from .report import _arms
from .runner import Store


def _flip(outcome: str) -> str:
    return {"x": "lost", "y": "won"}.get(outcome, "tie")


def rows(items: list[Item], store: Store) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in items:
        for arm in _arms(store):
            r = store.results.get((arm, item.id))
            if r is None:
                continue
            row: dict[str, Any] = {
                "item_id": item.id, "kind": item.kind, "question": item.text, "truth": item.label or "", "arm": arm,
                "label": r.label or "", "correct": ("" if (not item.label or r.error) else r.label == item.label),
                "stated_confidence": "" if r.confidence is None else round(r.confidence, 3),
                "seconds": round(r.seconds, 1), "cost_usd": round(r.cost, 5), "model_calls": r.calls,
                "words": words(r.text), "cites_verified": r.cites_verified, "cites_total": r.cites_total,
                "retrieved_n": r.retrieved_n, "failed": bool(r.error), "error": r.error or "",
            }
            if arm == "debate":
                x = r.extra
                tot = x.get("totals") or {}
                row.update({"debate_winner": x.get("winner", ""), "debate_for_total": tot.get("for", ""), "debate_against_total": tot.get("against", ""),
                            "debate_gap": x.get("gap", ""), "judge_runs": x.get("judge_samples", ""), "judge_agreement": x.get("agreement", ""),
                            "debate_end_reason": x.get("end_reason", ""),
                            "prose_conclusion": x.get("prose_conclusion") or "",
                            "prose_matches_winner": "" if x.get("prose_matches_winner") is None else x["prose_matches_winner"],
                            "prose_contradicts_winner": "" if x.get("prose_contradicts_winner") is None else x["prose_contradicts_winner"],
                            "proposition": x.get("proposition", "")})
            for (q, gx, gy), g in store.grades.items():
                if q != item.id or g.error:
                    continue
                if arm == gx:
                    row[f"overall_vs_{gy}"] = {"x": "won", "y": "lost"}.get(g.outcome.get("overall", "tie"), "tie")
                elif arm == gy:
                    row[f"overall_vs_{gx}"] = _flip(g.outcome.get("overall", "tie"))
            row["retrieved"] = r.retrieved  # full list in the JSON only; the CSV keeps the count
            row["text"] = r.text
            out.append(row)
    return out


def write(items: list[Item], store: Store, out_dir: str | Path) -> dict[str, Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    data = rows(items, store)
    fields: list[str] = []
    for row in data:
        for k in row:
            if k not in ("text", "retrieved") and k not in fields:
                fields.append(k)
    csv_path = out / "comparison.csv"
    with csv_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(data)
    json_path = out / "comparison.json"
    json_path.write_text(json.dumps(data, indent=1, default=str))
    md = ["# Side by side", ""]
    by_item: dict[str, list[dict[str, Any]]] = {}
    for row in data:
        by_item.setdefault(row["item_id"], []).append(row)
    for item in items:
        rs = by_item.get(item.id)
        if not rs:
            continue
        md += [f"## {item.id}: {item.text}", ""]
        if item.label:
            md += [f"Known answer: **{item.label}**", ""]
        md += ["| arm | answer | correct | seconds | cost | words | retrieved | cites (verified/total) |", "|---|---|---|---|---|---|---|---|"]
        for r in rs:
            ok = "" if r["correct"] == "" else ("yes" if r["correct"] else "no")
            md.append(f"| {r['arm']} | {r['label'] or '-'} | {ok or '-'} | {r['seconds']} | ${r['cost_usd']} | {r['words']} | {r.get('retrieved_n', 0)} | {r['cites_verified']}/{r['cites_total']} |")
        md.append("")
        for r in rs:
            vs = ", ".join(f"{k.removeprefix('overall_vs_')}: {v}" for k, v in r.items() if k.startswith("overall_vs_"))
            extra = f" (blind overall: {vs})" if vs else ""
            if r["arm"] == "debate" and r.get("debate_for_total") != "":
                extra += f" (judge: FOR {r['debate_for_total']} / AGAINST {r['debate_against_total']}, {r['judge_runs']} runs, agreement {r['judge_agreement']})"
            md += [f"### {r['arm']}{extra}", "", r["text"], ""]
    md_path = out / "side_by_side.md"
    md_path.write_text("\n".join(md))
    return {"csv": csv_path, "json": json_path, "markdown": md_path}
