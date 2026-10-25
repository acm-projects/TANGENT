"""Which model argues which side.

The client sends one model (used for both sides, the default) or two (sides are assigned at random, so a model's
strength can not be tied to a side by the way the request was written).
"""
from __future__ import annotations

import random
from typing import Optional


def assign_models(requested: list[str], rng: Optional[random.Random] = None) -> tuple[str, str, str]:
    """Returns (for_model, against_model, mode) where mode is 'same' or 'pair'."""
    models = list(dict.fromkeys(m.strip() for m in requested if m and m.strip()))  # drop blanks and repeats, keep order
    if not models or len(models) > 2:
        raise ValueError("send one model (both sides) or two models (sides assigned at random)")
    if len(models) == 1:
        return models[0], models[0], "same"
    rng = rng or random.SystemRandom()
    first, second = models
    return (first, second, "pair") if rng.random() < 0.5 else (second, first, "pair")
