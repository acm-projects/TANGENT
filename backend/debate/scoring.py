"""The verdict, computed in code.

The judge model does not pick the winner or write the confidence number. It labels every claim, scores three
criteria against written anchors, and writes the prose. Everything below is arithmetic on those labels, so the same
labels and scores always give the same winner and confidence.

    evidence    computed here from the claim labels (never asked of the model)
    scope       model, 0-10 against anchors
    engagement  model, 0-10 against anchors
    fidelity    model, 0-10 against anchors (sources described accurately, nothing overclaimed)

    total = 0.40 * evidence + 0.25 * scope + 0.25 * engagement + 0.10 * fidelity
"""
from __future__ import annotations

from typing import Any, Optional

WEIGHTS = {"evidence": 0.40, "scope": 0.25, "engagement": 0.25, "fidelity": 0.10}
MARGIN = 0.5  # totals must differ by at least this much for there to be a winner (confidence still reflects how close it was)
GAP_FOR_FULL_CREDIT = 3.0  # a lead this large earns the full 0.5 of the confidence for "how far ahead"
MIN_COVERAGE = 0.8  # share of claims the judge must label before the evidence score is trusted
LABEL_CREDIT = {"supported": 1.0, "partly_supported": 0.5, "unsupported": 0.0}
LABELS = ("supported", "partly_supported", "unsupported", "uncited")
CRITERIA = ("scope", "engagement", "fidelity")
SIDES = ("A", "B")


def _clamp(x: Any, lo: float = 0.0, hi: float = 10.0) -> float:
    try:
        return min(hi, max(lo, float(x)))
    except (TypeError, ValueError):
        return lo


def evidence_score(counts: dict[str, int]) -> float:
    """10 * (supported + 0.5 * partly) / (supported + partly + unsupported). Uncited claims are the debater's own
    reasoning, so they are neither credited nor penalised. No cited claims at all means no evidence: 0."""
    checked = sum(counts.get(k, 0) for k in LABEL_CREDIT)
    if checked == 0:
        return 0.0
    return 10.0 * sum(counts.get(k, 0) * w for k, w in LABEL_CREDIT.items()) / checked


def score_rubric(
    rubric: dict[str, Any],
    claims: dict[str, dict[str, Any]],
    cite_stats: dict[str, dict[str, int]],
    fixed_label: Optional[str] = None,
) -> dict[str, Any]:
    """claims: {"A1": {"label": "A", "cited": True}, ...}, built from the transcript, not from the model.
    cite_stats: {"A": {"total": n, "unverified": m}, "B": {...}} citation ids per side and how many are not real."""
    counts = {s: {k: 0 for k in LABELS} for s in SIDES}
    seen: set[str] = set()
    for chk in rubric.get("claim_checks") or []:
        cid = str(chk.get("claim", "")).strip().upper()
        lab = str(chk.get("label", "")).strip().lower()
        if cid in claims and cid not in seen and lab in LABELS:
            seen.add(cid)
            # The transcript, not the model, says whether a claim cites anything: an uncited claim cannot be "supported".
            if not claims[cid].get("cited"):
                lab = "uncited"
            counts[claims[cid]["label"]][lab] += 1
    coverage = (len(seen) / len(claims)) if claims else 1.0

    crit: dict[str, dict[str, float]] = {s: {} for s in SIDES}
    complete = True
    by_pos = {str(c.get("position", "")).strip().upper(): c for c in rubric.get("criteria") or []}
    for s in SIDES:
        row = by_pos.get(s)
        if not row:
            complete = False
        for k in CRITERIA:
            crit[s][k] = _clamp((row or {}).get(k, 0))
        crit[s]["evidence"] = round(evidence_score(counts[s]), 2)
    totals = {s: round(sum(WEIGHTS[k] * crit[s][k] for k in WEIGHTS), 2) for s in SIDES}

    gap = round(abs(totals["A"] - totals["B"]), 2)
    leader = "A" if totals["A"] >= totals["B"] else "B"
    judged = leader if (gap >= MARGIN and complete) else "none"

    total_cites = sum(cite_stats.get(s, {}).get("total", 0) for s in SIDES)
    bad_cites = sum(cite_stats.get(s, {}).get("unverified", 0) for s in SIDES)
    verified_share = (1 - bad_cites / total_cites) if total_cites else 0.0
    lead_claims = [i for i in claims.values() if i["label"] == leader]
    cited_share = (sum(1 for i in lead_claims if i.get("cited")) / len(lead_claims)) if lead_claims else 0.0
    confidence = 0.5 * min(1.0, gap / GAP_FOR_FULL_CREDIT) + 0.3 * verified_share + 0.2 * cited_share
    if judged == "none":
        confidence = min(confidence, 0.5)
    if not complete:
        confidence = 0.0

    leaning = str(rubric.get("leaning", "")).strip()
    leaning = leaning if leaning in ("A", "B", "none") else "none"
    return {
        "winner": fixed_label or judged,
        "would_have_chosen": judged,
        "confidence": round(confidence, 2),
        "totals": totals,
        "criteria": crit,
        "claim_counts": counts,
        "coverage": round(coverage, 2),
        "gap": gap,
        "margin": MARGIN,
        "weights": WEIGHTS,
        "complete": complete,
        "text_matches_scores": leaning == judged,
        "verified_share": round(verified_share, 2),
        "cited_share": round(cited_share, 2),
    }