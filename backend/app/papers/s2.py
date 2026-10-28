"""Semantic Scholar Graph API: paper search and lookup, normalized to the papers table's columns."""

import asyncio
import os
import time
from urllib.parse import quote

import httpx

S2_URL = os.getenv("S2_URL", "https://api.semanticscholar.org/graph/v1")
FIELDS = "paperId,title,authors,year,abstract,externalIds,openAccessPdf"

# Tests swap this for an httpx.MockTransport, as stream_openrouter's `transport` does.
transport: httpx.AsyncBaseTransport | None = None

# An S2 API key allows 1 request/second; one lock serializes every call in this process.
# shortcut: per-process, so N workers make N req/s; share the limit (Redis/Postgres) when scaling out.
_lock = asyncio.Lock()
_last = 0.0


class S2Error(Exception):
    """Semantic Scholar was unreachable or refused; the message is safe to show the model."""


async def _get(path: str, params: dict) -> dict | None:
    """GET one endpoint; None on 404. One retry on 429."""
    global _last
    headers = {"x-api-key": os.getenv("S2_API_KEY")} if os.getenv("S2_API_KEY") else {}
    async with _lock:
        for attempt in range(2):
            wait = _last + 1.0 - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            try:
                async with httpx.AsyncClient(timeout=10, transport=transport) as client:
                    r = await client.get(f"{S2_URL}{path}", params=params, headers=headers)
            except httpx.HTTPError as exc:
                raise S2Error(f"Semantic Scholar is unreachable ({type(exc).__name__})") from exc
            finally:
                _last = time.monotonic()
            if r.status_code == 429 and attempt == 0:
                continue
            if r.status_code in (400, 404):
                return None
            if r.status_code != 200:
                raise S2Error(f"Semantic Scholar returned HTTP {r.status_code}")
            return r.json()
    return None


def normalize(p: dict) -> dict:
    ids = p.get("externalIds") or {}
    arxiv = ids.get("ArXiv")
    pdf = (p.get("openAccessPdf") or {}).get("url") or (f"https://arxiv.org/pdf/{arxiv}" if arxiv else None)
    return {
        "source_id": p["paperId"],
        "title": p.get("title") or "(untitled)",
        "authors": [a["name"] for a in p.get("authors") or [] if a.get("name")],
        "year": p.get("year"),
        "abstract": p.get("abstract"),
        "doi": ids.get("DOI"),
        "arxiv_id": arxiv,
        "pdf_url": pdf or None,
    }


async def search(query: str, limit: int, year_from: int | None = None) -> list[dict]:
    params = {"query": query, "limit": limit, "fields": FIELDS}
    if year_from:
        params["year"] = f"{year_from}-"
    data = await _get("/paper/search", params)
    return [normalize(p) for p in (data or {}).get("data") or [] if p.get("paperId")]


async def get(ref: str) -> dict | None:
    """ref: an S2 paperId, "DOI:...", "ARXIV:..." or any id S2 accepts. It comes from the model, so it is
    escaped and kept to the /paper/ endpoint."""
    if not ref or ".." in ref:
        return None
    data = await _get(f"/paper/{quote(ref, safe=':/')}", {"fields": FIELDS})
    return normalize(data) if data and data.get("paperId") else None
