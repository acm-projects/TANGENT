"""Whether to ask the user a clarifying question before the debate starts, decided in code.

The model answers three yes/no questions about the topic (it is good at that and gives the same answer run to run);
the decision to ask is arithmetic on those answers, so the same topic always gets the same treatment.

    criterion_stated   the topic or the user's clarifications say what 'better', 'best' or 'worth it' is measured by
    setting_stated     they say for whom, or in what setting
    context_resolves   the project context or clarifications explicitly give whatever is missing (unrelated context does not count)

Ask when the criterion or the setting is missing and the context does not supply it. A short topic with a vague evaluative
word ('Is remote work better?') also counts as missing, even if the model says otherwise.
"""
from __future__ import annotations

import re
from typing import Optional

from .schemas import Question

VAGUE_WORDS = re.compile(r"\b(better|best|worse|worst|worth|worthwhile|good|bad|ideal|superior|recommend\w*|should i)\b", re.I)
SHORT_TOPIC_WORDS = 7
MAX_QUESTIONS = 2


def needs_question(topic: str, checks: dict[str, bool]) -> bool:
    if checks.get("context_resolves"):
        return False
    missing = not checks.get("criterion_stated", False) or not checks.get("setting_stated", False)
    vague_and_short = bool(VAGUE_WORDS.search(topic)) and len(topic.split()) <= SHORT_TOPIC_WORDS
    return missing or vague_and_short


def fallback_question(topic: str) -> Question:
    return Question(
        prompt="What should this debate use as the measure of 'better' or 'worth it'?",
        options=[{"label": "Cost and efficiency"}, {"label": "Quality and performance"}, {"label": "Risk and reliability"}, {"label": "Overall balance of these"}],
    )


def choose_questions(topic: str, checks: Optional[dict[str, bool]], proposed: list[Question]) -> list[Question]:
    """checks=None means the brain did not report any (older brains, tests): keep what it proposed."""
    if checks is None:
        return proposed
    if not needs_question(topic, checks):
        return []
    return (proposed or [fallback_question(topic)])[:MAX_QUESTIONS]
