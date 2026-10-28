"""Small, dependency-free statistics for comparing arms. Everything here is deterministic (the bootstrap takes a seed)."""
from __future__ import annotations

import math
import random
from typing import Optional, Sequence


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson interval for a proportion k/n. (0, 0) when n is 0."""
    if n <= 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, centre - half), min(1.0, centre + half))


def sign_test(wins: int, losses: int) -> float:
    """Two-sided exact binomial p-value for 'wins vs losses are equally likely' (ties are dropped by the caller).
    This is also the exact McNemar test for paired right/wrong results: wins = only A right, losses = only B right."""
    n = wins + losses
    if n == 0:
        return 1.0
    k = min(wins, losses)
    tail = sum(math.comb(n, i) for i in range(0, k + 1)) / (2 ** n)
    return min(1.0, 2 * tail)


def brier(pairs: Sequence[tuple[float, bool]]) -> Optional[float]:
    """Mean squared error between a stated probability of being right and whether the answer was right. Lower is better;
    always saying 50% scores 0.25."""
    if not pairs:
        return None
    return sum((p - (1.0 if ok else 0.0)) ** 2 for p, ok in pairs) / len(pairs)


def bootstrap_mean_ci(values: Sequence[float], *, iters: int = 2000, seed: int = 0) -> tuple[float, float]:
    """95% percentile bootstrap interval for the mean."""
    vals = list(values)
    if not vals:
        return (0.0, 0.0)
    rng = random.Random(seed)
    n = len(vals)
    means = sorted(sum(vals[rng.randrange(n)] for _ in range(n)) / n for _ in range(iters))
    return (means[int(0.025 * iters)], means[min(iters - 1, int(0.975 * iters))])


def win_rate(wins: int, losses: int, ties: int) -> dict:
    """Win rate with ties counted as half, its Wilson interval (on decided games) and the sign-test p-value."""
    n = wins + losses + ties
    rate = (wins + 0.5 * ties) / n if n else 0.0
    decided = wins + losses
    lo, hi = wilson(wins, decided)
    return {"n": n, "wins": wins, "losses": losses, "ties": ties, "rate": rate,
            "decided_ci": (lo, hi), "p": sign_test(wins, losses)}
