"""Live text for the client.

A debater answers with a tool call whose JSON arguments hold the whole turn (`thinking`, `argument`, `claims`). The judge
answers with one JSON object whose `final_output` is the text people read. Both arrive from the model as small fragments
of raw JSON. `FieldStreamer` pulls the text of one string field out of that JSON as it arrives, `StreamSink` batches it
(about every 250 ms) into `token` events, and the event table carries them to whichever process serves the SSE stream.

Streaming is best effort: a failed emit is logged and dropped, because the finished `turn_completed` / `verdict_ready`
event always carries the full text and replaces whatever was streamed.
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any, Awaitable, Callable, Optional

log = logging.getLogger(__name__)

_SIMPLE_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "b": "\b", "f": "\f", "/": "/", "\\": "\\", '"': '"'}


class FieldStreamer:
    """Incremental reader for ONE top-level string field of a JSON object that arrives in pieces.

    feed(fragment) returns the newly decoded characters of that field (possibly ""). Keys nested deeper than the top level
    are ignored, escapes (\\n, \\", \\uXXXX, surrogate pairs) are decoded even when split across fragments, and once the
    closing quote is seen the streamer is done and returns "" for everything after. A raw, unescaped quote inside the text
    (a known model slip) ends the field early; the finished event carries the repaired full text anyway."""

    def __init__(self, field: str) -> None:
        self.field = field
        self.depth = 0
        self.mode = "scan"  # scan | key | skip | value | done
        self.expect_key = False
        self.matched = False  # saw the key, waiting for its value
        self._key: list[str] = []
        self._esc = False
        self._uni: Optional[list[str]] = None
        self._high: Optional[int] = None

    @property
    def done(self) -> bool:
        return self.mode == "done"

    def feed(self, fragment: str) -> str:
        out: list[str] = []
        for ch in fragment:
            if self.mode == "done":
                break
            if self.mode == "value":
                self._value_char(ch, out)
            elif self.mode == "key":
                self._key_char(ch)
            elif self.mode == "skip":
                if self._esc:
                    self._esc = False
                elif ch == "\\":
                    self._esc = True
                elif ch == '"':
                    self.mode = "scan"
            else:
                self._scan_char(ch)
        return "".join(out)

    def _scan_char(self, ch: str) -> None:
        if ch.isspace() or ch == ":":
            return
        if ch == '"':
            if self.matched:
                self.matched = False
                self.mode = "value"
            elif self.depth == 1 and self.expect_key:
                self.expect_key = False
                self._key = []
                self.mode = "key"
            else:
                self.mode = "skip"
            return
        self.matched = False  # the field's value is not a string
        if ch in "{[":
            self.depth += 1
            if ch == "{" and self.depth == 1:
                self.expect_key = True
        elif ch in "}]":
            self.depth -= 1
        elif ch == "," and self.depth == 1:
            self.expect_key = True

    def _key_char(self, ch: str) -> None:
        if self._esc:
            self._esc = False
            self._key.append(ch)
        elif ch == "\\":
            self._esc = True
        elif ch == '"':
            self.matched = "".join(self._key) == self.field
            self.mode = "scan"
        else:
            self._key.append(ch)

    def _value_char(self, ch: str, out: list[str]) -> None:
        if self._uni is not None:
            self._uni.append(ch)
            if len(self._uni) == 4:
                digits, self._uni = "".join(self._uni), None
                try:
                    code = int(digits, 16)
                except ValueError:
                    out.append("�")
                    return
                self._unicode(code, out)
            return
        if self._esc:
            self._esc = False
            if ch == "u":
                self._uni = []
                return
            self._drop_high(out)
            out.append(_SIMPLE_ESCAPES.get(ch, ch))
            return
        if ch == "\\":
            self._esc = True
            return
        self._drop_high(out)
        if ch == '"':
            self.mode = "done"
        else:
            out.append(ch)

    def _drop_high(self, out: list[str]) -> None:
        if self._high is not None:  # a high surrogate that no low surrogate followed
            out.append("\ufffd")
            self._high = None

    def _unicode(self, code: int, out: list[str]) -> None:
        if self._high is not None:
            high, self._high = self._high, None
            if 0xDC00 <= code <= 0xDFFF:
                out.append(chr(0x10000 + ((high - 0xD800) << 10) + (code - 0xDC00)))
                return
            out.append("�")
        if 0xD800 <= code <= 0xDBFF:
            self._high = code
        elif 0xDC00 <= code <= 0xDFFF:
            out.append("�")
        else:
            out.append(chr(code))


EmitToken = Callable[[dict[str, Any], str], Awaitable[Any]]


class StreamSink:
    """Collects streamed text for one turn (or the judge's final answer) and emits it as `token` events.

    start() begins an attempt. The model client calls it again when it retries, and if the failed attempt already sent
    text the client is told to clear it (`reset: true`). push() buffers and flushes at most every `interval_s` seconds
    (the first text goes out at once so the box starts filling right away) or when `max_chars` pile up. close() flushes
    the rest. Event keys carry a per-sink nonce, so a turn re-run after a crash can never collide with, and be swallowed
    by, the rows of its earlier run.

    Writing to the database happens on a background task fed by a queue, so a slow database round trip can never hold up
    reading the model's stream (that would slow the debate down). close() waits until everything queued has been written,
    which keeps the `token` events ahead of the turn's finishing event. background=False writes inline (tests)."""

    def __init__(
        self,
        emit: EmitToken,
        meta: dict[str, Any],
        *,
        interval_s: float = 0.25,
        max_chars: int = 160,
        clock: Callable[[], float] = time.monotonic,
        background: bool = True,
    ) -> None:
        self._background = background
        self._queue: Optional[asyncio.Queue] = None
        self._writer: Optional[asyncio.Task] = None
        self._emit = emit
        self.meta = meta
        self.interval_s = interval_s
        self.max_chars = max_chars
        self._clock = clock
        self._nonce = uuid.uuid4().hex[:8]
        self._buf: list[str] = []
        self._size = 0
        self._last: Optional[float] = None
        self.attempt = 0
        self.seq = 0
        self._sent = False  # anything emitted in the current attempt

    async def start(self) -> None:
        had_text = self._sent
        self._buf, self._size, self._last, self.seq, self._sent = [], 0, None, 0, False
        self.attempt += 1
        if had_text:
            await self._send("", reset=True)

    async def push(self, text: str) -> None:
        if not text:
            return
        if self.attempt == 0:
            await self.start()
        self._buf.append(text)
        self._size += len(text)
        now = self._clock()
        if self._last is None or now - self._last >= self.interval_s or self._size >= self.max_chars:
            await self.flush()

    async def flush(self) -> None:
        if not self._buf:
            return
        text, self._buf, self._size = "".join(self._buf), [], 0
        self._last = self._clock()
        await self._send(text)

    async def close(self) -> None:
        await self.flush()
        if self._writer is not None and self._queue is not None:
            self._queue.put_nowait(None)
            await self._writer  # everything queued is written before the turn's finishing event goes out
            self._writer = self._queue = None

    async def _send(self, text: str, reset: bool = False) -> None:
        self.seq += 1
        payload = {**self.meta, "attempt": self.attempt, "seq": self.seq, "text": text}
        if reset:
            payload["reset"] = True
        else:
            self._sent = True
        key = f"tok:{self.meta.get('turn_id')}:{self._nonce}:{self.attempt}:{self.seq}"
        if not self._background:
            await self._write(payload, key)
            return
        if self._queue is None:
            self._queue = asyncio.Queue()
            self._writer = asyncio.create_task(self._drain(self._queue))
        self._queue.put_nowait((payload, key))

    async def _drain(self, queue: "asyncio.Queue") -> None:
        """Write queued pieces one database round trip at a time. Pieces that piled up while a write was in flight are
        merged into one write (same attempt, no reset between them), so a slow database makes the live text slightly
        chunkier instead of building a backlog that the end of the turn would have to wait for."""
        finished = False
        while not finished:
            batch = [await queue.get()]
            while not queue.empty():
                batch.append(queue.get_nowait())
            pending: Optional[tuple[dict[str, Any], str]] = None
            for item in batch:
                if item is None:
                    finished = True
                    break
                payload, key = item
                if (pending is not None and not payload.get("reset") and not pending[0].get("reset")
                        and payload["attempt"] == pending[0]["attempt"]):
                    pending = ({**payload, "text": pending[0]["text"] + payload["text"]}, key)
                else:
                    if pending is not None:
                        await self._write(*pending)
                    pending = (payload, key)
            if pending is not None:
                await self._write(*pending)

    async def _write(self, payload: dict[str, Any], key: str) -> None:
        try:
            await self._emit(payload, key)
        except Exception:  # streaming must never take a debate down
            log.warning("token event dropped", exc_info=True)


class FieldTap:
    """Connects the model client to a sink: `source` says where the field lives ("tool" = the first tool call's
    arguments, "content" = the message text), `field` which string to stream."""

    def __init__(self, field: str, sink: StreamSink, source: str) -> None:
        if source not in ("tool", "content"):
            raise ValueError("source must be 'tool' or 'content'")
        self.field, self.sink, self.source = field, sink, source
        self._ex = FieldStreamer(field)

    async def start(self) -> None:
        self._ex = FieldStreamer(self.field)
        await self.sink.start()

    async def feed(self, fragment: str) -> None:
        text = self._ex.feed(fragment)
        if text:
            await self.sink.push(text)


def turn_id(debate_id: str, side: str, phase: str, rnd: int) -> str:
    return f"{debate_id}:{side}:{phase}:{rnd}"


def make_sink(deps: Any, debate_id: str, side: str, phase: str, rnd: int) -> Optional[StreamSink]:
    """None when streaming is off (tests, or a deployment that turned it off)."""
    if not getattr(deps, "stream_tokens", False):
        return None

    async def emit(payload: dict[str, Any], key: str) -> Any:
        return await deps.emitter.emit("token", payload, key=key)

    meta = {"turn_id": turn_id(debate_id, side, phase, rnd), "side": side, "phase": phase, "round": rnd}
    return StreamSink(emit, meta, interval_s=getattr(deps, "stream_interval_s", 0.25))
