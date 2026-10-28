"""Semantic Scholar Graph API client for the debaters' `search_papers` tool.

Key from S2_API_KEY (header x-api-key). A key allows 1 request per second, and both debaters search in parallel,
so every request goes through one shared throttle; a 429 is retried with backoff.
"""
from __future__ import annotations

import asyncio
import os
import time
from typing import Any, Optional

import httpx

from .schemas import Evidence

BASE = "https://api.semanticscholar.org/graph/v1"
FIELDS = "title,year,abstract,url,tldr,citationCount"


class SemanticScholarSearch:
    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        limit: int = 5,
        min_interval: float = 1.1,
        retries: int = 3,
        client: Optional[httpx.AsyncClient] = None,
        sleep: Any = asyncio.sleep,
    ) -> None:
        self.key, self.limit, self.gap, self.retries, self._sleep = api_key, limit, min_interval, retries, sleep
        self.client = client or httpx.AsyncClient(timeout=20)
        self._lock = asyncio.Lock()
        self._last = 0.0

    async def _throttle(self) -> None:
        async with self._lock:
            wait = self._last + self.gap - time.monotonic()
            if wait > 0:
                await self._sleep(wait)
            self._last = time.monotonic()

    async def search(self, query: str) -> list[Evidence]:
        headers = {"x-api-key": self.key} if self.key else {}
        params = {"query": query, "limit": str(self.limit), "fields": FIELDS}
        for attempt in range(self.retries + 1):
            await self._throttle()
            r = await self.client.get(f"{BASE}/paper/search", params=params, headers=headers)
            if r.status_code == 429 or r.status_code >= 500:
                if attempt < self.retries:
                    await self._sleep(2 ** attempt)
                    continue
            r.raise_for_status()
            return [e for e in (_evidence(p) for p in r.json().get("data") or []) if e]
        return []


ABSTRACT_CHARS = 1000


def _clip(text: str, limit: int) -> str:
    """Cut at a word boundary and mark it, so the model knows the abstract continues and does not infer from silence."""
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0].rstrip(",;:.") + " …"


def _evidence(p: dict[str, Any]) -> Optional[Evidence]:
    pid, title = p.get("paperId"), (p.get("title") or "").strip()
    if not pid or not title:
        return None
    # The real abstract, not the one-sentence TLDR: debaters misread methods and scope from a single summary line.
    # The TLDR is only a fallback for papers with no abstract.
    tldr = (p.get("tldr") or {}).get("text")
    snippet = _clip((p.get("abstract") or tldr or "").strip(), ABSTRACT_CHARS)
    cites = p.get("citationCount")
    if cites is not None:
        snippet = f"{snippet} (cited {cites} times)".strip()
    return Evidence(
        id=f"s2-{pid[:12]}",
        title=title,
        year=p.get("year"),
        url=p.get("url") or f"https://www.semanticscholar.org/paper/{pid}",
        snippet=snippet,
    )


def from_env() -> SemanticScholarSearch:
    return SemanticScholarSearch(os.environ.get("S2_API_KEY"))


class CachedSearch:
    """Wraps any Search with a small in-memory cache keyed on the normalised query, so the same query asked twice (by
    the other side, in a later round, or in another debate served by the same process) costs nothing. Concurrent
    identical queries share one call. Failures are never cached."""

    def __init__(self, inner, *, ttl_s: float = 3600.0, max_items: int = 256, clock=None) -> None:
        import time as _t
        self._inner, self._ttl, self._max = inner, ttl_s, max_items
        self._clock = clock or _t.monotonic
        self._done: dict = {}
        self._inflight: dict = {}
        self.hits = 0
        self.misses = 0

    @staticmethod
    def _key(query: str) -> str:
        return " ".join(query.lower().split())

    async def search(self, query: str):
        import asyncio
        key = self._key(query)
        hit = self._done.get(key)
        if hit is not None and self._clock() - hit[0] < self._ttl:
            self.hits += 1
            return list(hit[1])
        task = self._inflight.get(key)
        if task is None:
            self.misses += 1
            task = asyncio.ensure_future(self._inner.search(query))
            self._inflight[key] = task
        else:
            self.hits += 1
        try:
            results = await asyncio.shield(task)
        finally:
            if task.done():
                self._inflight.pop(key, None)
        if key not in self._done and len(self._done) >= self._max:
            self._done.pop(next(iter(self._done)))
        self._done[key] = (self._clock(), list(results))
        return list(results)
