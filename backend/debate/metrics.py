from __future__ import annotations

from typing import Any, Iterable, Optional

from .schemas import Usage

TOKEN_FIELDS = ("prompt_tokens", "completion_tokens", "reasoning_tokens", "cached_tokens")


def usage_record(usage: Optional[Usage], **ctx: Any) -> list[dict[str, Any]]:
    if usage is None:
        return []
    return [{**usage.model_dump(), **{k: v for k, v in ctx.items() if v is not None}}]


def _blank() -> dict[str, Any]:
    return {"calls": 0, "attempts": 0, "cost": 0.0, **{f: 0 for f in TOKEN_FIELDS}, "latency_ms": 0}


def _add(into: dict[str, Any], rec: dict[str, Any]) -> None:
    into["calls"] += 1
    into["attempts"] += int(rec.get("attempts") or 1)
    into["cost"] = round(into["cost"] + float(rec.get("cost") or 0), 8)
    into["latency_ms"] += int(rec.get("latency_ms") or 0)
    for f in TOKEN_FIELDS:
        into[f] += int(rec.get(f) or 0)


def total_cost(usage: Iterable[dict[str, Any]]) -> float:
    return round(sum(float(u.get("cost") or 0) for u in usage), 8)


def summarize_usage(usage: Iterable[dict[str, Any]]) -> dict[str, Any]:
    total = _blank()
    by_role: dict[str, dict[str, Any]] = {}
    by_model: dict[str, dict[str, Any]] = {}
    for rec in usage:
        _add(total, rec)
        _add(by_role.setdefault(rec.get("role") or "unknown", _blank()), rec)
        _add(by_model.setdefault(rec.get("model") or "unknown", _blank()), rec)
    total["total_tokens"] = total["prompt_tokens"] + total["completion_tokens"]
    return {"total": total, "by_role": by_role, "by_model": by_model}


def summarize_timings(metrics: Iterable[dict[str, Any]]) -> dict[str, Any]:
    by_node: dict[str, dict[str, Any]] = {}
    spans: dict[str, list[int]] = {}
    for m in metrics:
        node = m["node"]
        slot = by_node.setdefault(node, {"count": 0, "total_ms": 0, "max_ms": 0})
        slot["count"] += 1
        slot["total_ms"] += m["duration_ms"]
        slot["max_ms"] = max(slot["max_ms"], m["duration_ms"])
        phase = m.get("phase")
        if phase in ("research", "opening", "rebuttal", "closing") and m.get("started_at_ms"):
            key = f"{phase}:{m.get('round') or 0}"
            start, end = m["started_at_ms"], m["started_at_ms"] + m["duration_ms"]
            lo, hi = spans.setdefault(key, [start, end])
            spans[key] = [min(lo, start), max(hi, end)]
    phases = {k: {"seconds": round((hi - lo) / 1000, 3), "started_at_ms": lo} for k, (lo, hi) in spans.items()}
    return {"by_node": by_node, "phases": phases}