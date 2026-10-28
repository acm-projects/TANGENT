"""A scripted stand-in for OpenRouterClient, so the harness can be tested and smoke-run with no keys and no network."""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Callable, Optional

from debate.openrouter import ChatResult
from debate.schemas import Usage


def _h(text: str) -> int:
    return int(hashlib.sha1(text.encode()).hexdigest(), 16)


class FakeClient:
    """Answers by prompt shape. `claim_answer(claim) -> 'TRUE'|'FALSE'|'UNSURE'` decides claim verdicts; `prefer(a, b) -> '1'|'2'|'tie'`
    decides grader picks from the two answer texts (default: the longer one wins, ties stay ties)."""

    def __init__(self, claim_answer: Optional[Callable[[str], str]] = None, prefer: Optional[Callable[[str, str], str]] = None,
                 cost: float = 0.001, polarity: str = "same", position_bias: Optional[str] = None,
                 empty_first: int = 0, always_empty: bool = False) -> None:
        # empty_first / always_empty reproduce a model that spends its whole token budget on reasoning and returns no text.
        self.empty_first, self.always_empty, self._empties = empty_first, always_empty, 0
        self.claim_answer = claim_answer or (lambda c: "TRUE" if _h(c) % 2 else "FALSE")
        self.prefer = prefer or (lambda a, b: "1" if len(a) > len(b) else "2" if len(b) > len(a) else "tie")
        self.cost, self.polarity, self.position_bias = cost, polarity, position_bias
        self.calls: list[dict[str, Any]] = []

    def _res(self, content: str) -> ChatResult:
        return ChatResult(id="fake", message={"content": content}, usage=Usage(model="fake", cost=self.cost, latency_ms=1), finish_reason="stop")

    async def chat(self, *, model: str, messages: list[dict[str, Any]], **kw: Any) -> ChatResult:
        self.calls.append({"model": model, "messages": messages, **kw})
        if self.always_empty or self._empties < self.empty_first:
            self._empties += 1
            return ChatResult(id="fake", message={"content": ""},
                              usage=Usage(model="fake", cost=self.cost, latency_ms=1, reasoning_tokens=777),
                              finish_reason="length")
        p = messages[-1]["content"]
        if "You are grading two answers" in p:
            a = re.search(r"<answer_1>\n(.*?)\n</answer_1>", p, re.S).group(1)
            b = re.search(r"<answer_2>\n(.*?)\n</answer_2>", p, re.S).group(1)
            pick = self.position_bias or self.prefer(a, b)
            return self._res(json.dumps({c: pick for c in ("accuracy", "balance", "calibration", "usefulness", "overall")} | {"reason": "r"}))
        if "Negate this scientific claim" in p:
            claim = re.search(r"Claim: (.*?)\n", p).group(1)
            return self._res(json.dumps({"negated": f"It is not the case that {claim}"}))
        if p.startswith("Write up to"):
            return self._res(json.dumps({"queries": ["query one", "query two"]}))
        if "arguing that the claim is true" in p:
            return self._res(self.polarity)
        m = re.search(r"Claim: (.*?)\n", p)
        if m and "VERDICT" in p:
            v = self.claim_answer(m.group(1))
            return self._res(f"Reasoning about it.\nVERDICT: {v}\nCONFIDENCE: 80")
        return self._res("A plain answer. " * 20)
