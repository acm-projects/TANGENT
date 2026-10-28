"""Questions to run. Two kinds:

claims   a statement with a known true/false answer, so every arm can be scored by accuracy with no judge at all.
topics   open questions like the ones users ask ("Is a four-day week better?"), graded blind by other models.

Files are JSON Lines. A claim: {"id": "c1", "text": "...", "label": "true" | "false"}. A topic: {"id": "t1", "text": "..."}.
"""
from __future__ import annotations

import asyncio
import json
import random
import tarfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

DATA = Path(__file__).parent / "data"
SCIFACT_URL = "https://scifact.s3-us-west-2.amazonaws.com/release/latest/data.tar.gz"  # public release of the SciFact dataset (Wadden et al. 2020)


@dataclass
class Item:
    id: str
    text: str
    label: Optional[str] = None  # "true" | "false" for claims, None for topics

    @property
    def kind(self) -> str:
        return "claim" if self.label else "topic"


def load(path: str | Path) -> list[Item]:
    items: list[Item] = []
    for n, line in enumerate(Path(path).read_text().splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        d = json.loads(line)
        label = d.get("label")
        if label is not None:
            label = str(label).strip().lower()
            if label not in ("true", "false"):
                raise ValueError(f"{path}:{n}: label must be 'true' or 'false', got {label!r}")
        if not str(d.get("text", "")).strip():
            raise ValueError(f"{path}:{n}: missing text")
        items.append(Item(id=str(d.get("id") or f"i{n}"), text=str(d["text"]).strip(), label=label))
    ids = [i.id for i in items]
    if len(set(ids)) != len(ids):
        raise ValueError(f"{path}: duplicate ids")
    return items


def sample(items: list[Item], n: Optional[int], seed: int = 0) -> list[Item]:
    """A reproducible sample, balanced between true and false claims when both exist."""
    if not n or n >= len(items):
        return list(items)
    rng = random.Random(seed)
    if all(i.label for i in items):
        by = {"true": [i for i in items if i.label == "true"], "false": [i for i in items if i.label == "false"]}
        for v in by.values():
            rng.shuffle(v)
        half = n // 2
        picked = by["true"][: n - half] + by["false"][:half]
        short = n - len(picked)
        if short > 0:
            rest = [i for i in items if i not in picked]
            rng.shuffle(rest)
            picked += rest[:short]
        rng.shuffle(picked)
        return picked
    picked = list(items)
    rng.shuffle(picked)
    return picked[:n]


def fetch_scifact(dest: str | Path, *, per_label: int = 100, seed: int = 0) -> Path:
    """Download SciFact and write claims.jsonl (SUPPORT -> true, CONTRADICT -> false) to dest.

    SciFact claims are written by scientists about biomedical papers; each is labelled by experts against paper abstracts.
    Claims with mixed or missing evidence are dropped, so every label here is one expert-checked answer. Run this once
    on your machine (the download is a few MB)."""
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    tgz = dest / "scifact.tar.gz"
    if not tgz.exists():
        urllib.request.urlretrieve(SCIFACT_URL, tgz)  # noqa: S310 - fixed https URL
    with tarfile.open(tgz) as tf:
        member = next(m for m in tf.getmembers() if m.name.endswith("claims_dev.jsonl"))
        raw = tf.extractfile(member).read().decode()  # type: ignore[union-attr]
    rows = []
    for line in raw.splitlines():
        d = json.loads(line)
        labels = {e["label"] for ev in (d.get("evidence") or {}).values() for e in ev}
        if labels == {"SUPPORT"}:
            rows.append(("true", d))
        elif labels == {"CONTRADICT"}:
            rows.append(("false", d))
    rng = random.Random(seed)
    out = []
    for lab in ("true", "false"):
        pool = [d for l, d in rows if l == lab]
        rng.shuffle(pool)
        out += [{"id": f"sf{d['id']}", "text": d["claim"], "label": lab} for d in pool[:per_label]]
    rng.shuffle(out)
    path = dest / "scifact_claims.jsonl"
    path.write_text("\n".join(json.dumps(o) for o in out) + "\n")
    return path


# ---------------------------------------------------------------------------------------------------------------
# Negation: the test that separates "these claims are hard" from "the scoring favours one side".
#
# Every debate in the first pilot came down AGAINST, and the AGAINST side won the judge's totals 6 times out of 6.
# Two explanations fit that: the claims genuinely were unsupported, or the rubric rewards whoever argues "the evidence
# does not establish this". Negating each claim separates them. A false claim's negation is true, so the correct answer
# flips to FOR. If AGAINST still wins most debates on the negated set, the bias is in the scoring, not in the claims.
# ---------------------------------------------------------------------------------------------------------------
NEGATE_PROMPT = """Negate this scientific claim.

Claim: {claim}

Write the claim's direct logical opposite: same subject, same specifics, opposite assertion. Keep every entity, measure,
population and condition exactly as written, including any typos or odd spellings. Change only what is asserted. Do not
hedge ("may not", "is unclear"), do not add qualifiers, and do not comment on whether either version is true.

Reply with JSON only: {{"negated": "..."}}"""

FLIP = {"true": "false", "false": "true"}


async def negate(client: Any, model: str, items: list[Item], *, concurrency: int = 4) -> tuple[list[Item], float]:
    """Each labelled item with its claim negated and its label flipped. Returns (items, cost).

    Topics are passed through unchanged (there is nothing to negate). An item whose negation cannot be read back is
    dropped rather than guessed at, so a failed negation never silently becomes a mislabelled claim.
    """
    from debate.openrouter import lenient_loads

    sem = asyncio.Semaphore(max(1, concurrency))
    spent = [0.0]

    async def one(item: Item) -> Optional[Item]:
        if not item.label:
            return item
        async with sem:
            res = await client.chat(model=model, max_tokens=800,
                                    messages=[{"role": "user", "content": NEGATE_PROMPT.format(claim=item.text)}])
        spent[0] += res.usage.cost
        try:
            text = str(lenient_loads(res.message.get("content") or "")["negated"]).strip()
        except (ValueError, KeyError, TypeError):
            return None
        if not text or text.lower() == item.text.lower():
            return None
        return Item(id=f"{item.id}-neg", text=text, label=FLIP[item.label])

    got = await asyncio.gather(*[one(i) for i in items])
    return [i for i in got if i is not None], spent[0]
