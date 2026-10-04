"""SSE framing; event names/shapes mirror frontend/src/api/stream.ts."""

import json
from typing import AsyncIterator, Awaitable, Callable


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


async def stream_events(
    chunks: AsyncIterator[str],
    on_done: Callable[[str], Awaitable[None]],
) -> AsyncIterator[str]:
    """token per chunk, then done. on_done(full_reply) runs before `done` so the
    endpoint can persist the reply; on any failure emit `error` and never `done`."""
    parts: list[str] = []
    try:
        async for c in chunks:
            parts.append(c)
            yield sse("token", {"text": c})
        await on_done("".join(parts))
    except Exception as e:  # noqa: BLE001 - any upstream/persist failure must reach the client
        yield sse("error", {"message": str(e) or type(e).__name__})
        return
    yield sse("done", {})
