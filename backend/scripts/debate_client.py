#!/usr/bin/env python3
"""Run a debate through the real HTTP API from the terminal, answering its questions interactively.

Start one:
    python3 scripts/debate_client.py --user-id <uuid> --project <uuid> --node <uuid> --topic "Is it worth it?"

Pick up one that is already running or waiting for an answer:
    python3 scripts/debate_client.py --user-id <uuid> --resume <debate-id>

Authentication (first match wins):
    --token / $DEBATE_TOKEN       an access token you already have
    --user-id                     mint a token with the backend's own secret (run from backend/ so `app` imports)

Nothing here prints a token or a key.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import textwrap
import threading
import time
from typing import Any, Callable, Iterator, Optional

import httpx

DEFAULT_MODEL = "anthropic/claude-haiku-5.5"
TERMINAL = {"completed", "failed", "cancelled", "expired"}


# ---------------------------------------------------------------- SSE parsing
def parse_sse(lines: Iterator[str]) -> Iterator[dict[str, Any]]:
    """Turn raw SSE lines into {event, id, data} dicts. Comment lines (pings) are skipped."""
    event, eid, data = "message", None, []
    for line in lines:
        line = line.rstrip("\r\n")
        if line == "":
            if data:
                try:
                    payload = json.loads("\n".join(data))
                except ValueError:
                    payload = {"raw": "\n".join(data)}
                yield {"event": event, "id": eid, "data": payload}
            event, eid, data = "message", None, []
        elif line.startswith(":"):
            continue
        elif line.startswith("event:"):
            event = line[6:].strip()
        elif line.startswith("id:"):
            eid = line[3:].strip()
        elif line.startswith("data:"):
            data.append(line[5:].lstrip())


# ------------------------------------------------------------------ questions
def ask_questions(questions: list[dict[str, Any]], auto: bool, read: Callable[[str], str] = input) -> Optional[dict[str, Any]]:
    """Return {question_id: answer}, or None if the user typed 'skip'."""
    answers: dict[str, Any] = {}
    for q in questions:
        opts = [o.get("label", "") for o in (q.get("options") or [])]
        multi = q.get("type") == "multi"
        print(f"\n? {q['prompt']}" + ("   (pick several, e.g. 1,3)" if multi else ""))
        for i, o in enumerate(opts, 1):
            print(f"   {i}. {o}")
        if q.get("allow_other", True):
            print("   or type your own answer, or 'skip' to let the debate decide")
        if auto:
            pick = opts[0] if opts else "no preference"
            answers[q["id"]] = [pick] if multi else pick
            print(f"> (auto) {pick}")
            continue
        while True:
            raw = read("> ").strip()
            if raw.lower() == "skip":
                return None
            if not raw:
                continue
            if multi and all(p.strip().isdigit() for p in raw.split(",")):
                idx = [int(p) for p in raw.split(",")]
                if all(0 < i <= len(opts) for i in idx):
                    answers[q["id"]] = [opts[i - 1] for i in idx]
                    break
                print("   number out of range")
                continue
            if raw.isdigit():
                n = int(raw)
                if 0 < n <= len(opts):
                    answers[q["id"]] = [opts[n - 1]] if multi else opts[n - 1]
                    break
                print("   number out of range")
                continue
            if q.get("allow_other", True):
                answers[q["id"]] = [raw] if multi else raw
                break
            print("   pick one of the numbered options")
    return answers


# ------------------------------------------------------------------ live text
class Live:
    """The stage: one debater speaks at a time, and both debaters' working notes show at the same time.

    The server lets FOR and AGAINST write in parallel (that is faster), so text for both arrives interleaved. A person
    can only read one, so this class plays the turns back one after another, in the order their first text arrived. The
    speaker's text is shown as it arrives (never faster than TYPE_CPS, and faster when a large backlog has built up);
    the other side's text waits, already written, until its turn. A turn's finished summary, and every other line that
    would print after it, waits until the turn has been spoken, so the log reads in speaking order.

    Nothing is drawn unless the output is a terminal. All printing goes through turn_done() / after() so the stage is
    erased and redrawn around it. Everything is guarded by one lock because tick() runs on a background thread."""

    TYPE_CPS = 400.0       # characters per second when the speaker is replaying text that is already there
    CATCH_UP_CPS = 1500.0  # when more than BIG_BACKLOG characters are waiting
    BIG_BACKLOG = 1500

    def __init__(self, out: Any = None, *, enabled: Optional[bool] = None, max_lines: int = 12,
                 width: Optional[int] = None, rows: Optional[int] = None, clock: Callable[[], float] = time.monotonic) -> None:
        self.out = out or sys.stdout
        self.enabled = self.out.isatty() if enabled is None else enabled
        self.max_lines, self.width, self.rows, self.clock = max_lines, width, rows, clock
        self.lock = threading.RLock()
        self.turns: dict[str, dict[str, Any]] = {}
        self.order: list[str] = []   # turn ids in the order their first text arrived; the head is the speaker
        self.done: set[str] = set()  # turns already spoken and printed (replayed tokens for them are ignored)
        self.notes: dict[str, str] = {}
        self.barriers: list[tuple[set[str], Callable[[], None]]] = []
        self.drawn = 0
        self._last: list[str] = []
        self._tick_at = clock()
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    # ---- feeding
    def token(self, p: dict[str, Any]) -> None:
        tid = p.get("turn_id")
        if not self.enabled or not tid:
            return
        with self.lock:
            if tid in self.done:
                return
            t = self.turns.get(tid)
            if t is None:
                t = self.turns[tid] = {"side": p.get("side"), "phase": p.get("phase"), "round": p.get("round"),
                                       "got": "", "shown": 0.0, "final": None, "cb": None}
                self.order.append(tid)
            if p.get("reset"):
                t["got"], t["shown"] = "", 0.0
            t["got"] += p.get("text") or ""

    def note(self, side: Optional[str], text: Any) -> None:
        if self.enabled and side and text:
            with self.lock:
                self.notes[str(side)] = str(text)

    def turn_done(self, tid: Optional[str], final: Optional[str], cb: Callable[[], None]) -> None:
        """The turn's finished event arrived. cb prints its summary; it runs once the turn has been spoken."""
        with self.lock:
            t = self.turns.get(tid) if tid else None
            if not self.enabled or t is None:
                self._run(cb)
                return
            if final is not None:
                t["final"] = final
                t["shown"] = min(t["shown"], float(len(final)))
            else:
                t["final"] = t["got"]
            t["cb"] = cb
            self.notes.pop(str(t["side"]), None)

    def after(self, cb: Callable[[], None]) -> None:
        """Run cb after every turn already on the stage has been spoken and printed (at once if the stage is empty)."""
        with self.lock:
            waits = set(self.turns)
            if not self.enabled or (not waits and not self.barriers):
                self._run(cb)
            else:
                self.barriers.append((waits, cb))

    def drain(self) -> None:
        """Skip the animation: print everything that is waiting, in speaking order. Used before a question and at the end."""
        with self.lock:
            for tid in list(self.order):
                t = self.turns[tid]
                if t["cb"] is None:
                    t["final"] = t["got"]
                    t["cb"] = lambda: None
                t["shown"] = float(len(t["final"] or ""))
                self._finish(tid)
            self._run_barriers()
            self.erase()

    # ---- playing
    def tick(self) -> None:
        with self.lock:
            if not self.enabled:
                return
            now = self.clock()
            dt = min(0.5, max(0.0, now - self._tick_at))
            self._tick_at = now
            changed = False
            cur = self.order[0] if self.order else None
            if cur is not None:
                t = self.turns[cur]
                text = t["final"] if t["final"] is not None else t["got"]
                backlog = len(text) - int(t["shown"])
                if backlog > 0:
                    cps = self.CATCH_UP_CPS if backlog > self.BIG_BACKLOG else self.TYPE_CPS
                    t["shown"] = min(float(len(text)), t["shown"] + max(1.0, cps * dt))
                    changed = True
                if t["final"] is not None and int(t["shown"]) >= len(t["final"]):
                    self._finish(cur)
                    changed = True
            if self._run_barriers():
                changed = True
            lines = self.frame()
            if (lines != self._last and (lines or self.drawn)) or (lines and not self.drawn) or changed and lines:
                self.redraw()

    def _finish(self, tid: str) -> None:
        t = self.turns.pop(tid)
        self.order.remove(tid)
        self.done.add(tid)
        self._run(t["cb"] or (lambda: None))

    def _run_barriers(self) -> bool:
        ran = False
        while self.barriers and not (self.barriers[0][0] & set(self.turns)):
            _, cb = self.barriers.pop(0)
            self._run(cb)
            ran = True
        return ran

    def _run(self, cb: Callable[[], None]) -> None:
        with self.lock:
            self.erase()
            cb()

    # ---- drawing
    def _cols(self) -> int:
        return self.width or shutil.get_terminal_size((100, 24)).columns

    def _rows(self) -> int:
        return self.rows or shutil.get_terminal_size((100, 24)).lines

    def frame(self) -> list[str]:
        cols = self._cols()
        body_n = max(3, min(self.max_lines, self._rows() - 8))  # the stage must always fit on the screen
        out: list[str] = []
        if self.order:
            t = self.turns[self.order[0]]
            label = "JUDGE" if t["side"] == "judge" else f"{str(t['side']).upper()} | {t['phase']} {t['round']}"
            head = f"{label} is speaking"
            waiting = [self.turns[x] for x in self.order[1:]]
            if waiting:
                head += "    next: " + ", ".join(f"{str(w['side']).upper()} ({len(w['got'])} chars ready)" for w in waiting)
            text = (t["final"] if t["final"] is not None else t["got"])[: int(t["shown"])]
            lines: list[str] = []
            for para in text.split("\n"):
                lines += textwrap.wrap(para, cols - 1) or [""]
            body = lines[-body_n:]
            out += [head, "-" * (cols - 1)] + body + [""] * (body_n - len(body))
        for side in ("for", "against"):
            if side in self.notes:
                out.append(f"{side.upper():8}thinking: {self.notes[side]}")
        return [ln[: cols - 1] for ln in out]

    def erase(self) -> None:
        with self.lock:
            if self.enabled and self.drawn:
                self.out.write(f"\x1b[{self.drawn}A\x1b[J")
                self.out.flush()
            self.drawn = 0

    def redraw(self) -> None:
        with self.lock:
            if not self.enabled:
                return
            self.erase()
            lines = self.frame()
            if lines:
                self.out.write("\n".join(lines) + "\n")
                self.out.flush()
            self.drawn = len(lines)
            self._last = lines

    # ---- the background clock
    def start(self) -> None:
        if not self.enabled or self._thread is not None:
            return

        def loop() -> None:
            while not self._stop.wait(0.06):
                try:
                    self.tick()
                except Exception:  # drawing must never take the client down
                    pass

        self._thread = threading.Thread(target=loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1)
            self._thread = None
        self.erase()


# --------------------------------------------------------------------- output
def show(ev: dict[str, Any], verbose: bool) -> None:
    t, d = ev["event"], ev["data"]
    p = d.get("payload", {}) if isinstance(d, dict) else {}
    if t == "phase_changed":
        extra = f" round {p['round']}" if p.get("round") else ""
        print(f"\n[{p.get('phase')}{extra}]")
    elif t == "tool_called":
        print(f"  {p.get('side', '?'):7} searches: {p.get('query')}")
    elif t == "thinking":
        if verbose:
            print(f"  {p.get('side', '?'):7} thinking: {p.get('text')}")
    elif t == "turn_completed":
        text = (p.get("argument") or "").strip().replace("\n", " ")
        cut = " (cut short)" if p.get("truncated") else ""
        print(f"\n== {str(p.get('side')).upper()} | {p.get('phase')} {p.get('round')}{cut} ==")
        print(text if verbose else (text[:400] + (" ..." if len(text) > 400 else "")))
    elif t == "answer_received":
        print("\n[answer received, resuming]")
    elif t == "failed" or t == "error":
        print(f"\n[{t}] {json.dumps(p)[:300]}")


def usage_lines(v: dict[str, Any]) -> list[str]:
    """Cost, tokens and time for the debate, from the stored result."""
    us = v.get("usage_summary") or {}
    tot = us.get("total") or {}
    ts = v.get("timing_summary") or {}
    out: list[str] = []
    wall, active, waited = v.get("wall_ms"), v.get("active_ms"), v.get("waited_ms")
    if wall is not None:
        out.append(f"Time        : {round(wall / 1000, 1)} s wall, {round((active or 0) / 1000, 1)} s working, {round((waited or 0) / 1000, 1)} s waiting for you")
    cost = v.get("cost_usd")
    if cost is not None or tot:
        out.append(
            f"Cost        : ${float(cost if cost is not None else tot.get('cost') or 0):.4f}   "
            f"tokens {tot.get('total_tokens', 0):,} (in {tot.get('prompt_tokens', 0):,}, out {tot.get('completion_tokens', 0):,}, "
            f"reasoning {tot.get('reasoning_tokens', 0):,}, cached {tot.get('cached_tokens', 0):,})   "
            f"{tot.get('calls', 0)} model calls ({tot.get('attempts', 0)} attempts)"
        )
    for role, r in (us.get("by_role") or {}).items():
        out.append(f"  {role:8} ${r.get('cost', 0):.4f}  {r.get('prompt_tokens', 0) + r.get('completion_tokens', 0):,} tokens  {r.get('calls', 0)} calls  {round(r.get('latency_ms', 0) / 1000, 1)} s of model time")
    for key, ph in sorted((ts.get("phases") or {}).items()):
        out.append(f"  phase {key:12} {ph.get('seconds')} s")
    for node, n in (ts.get("by_node") or {}).items():
        out.append(f"  step  {node:12} {n.get('count')}x  total {round(n.get('total_ms', 0) / 1000, 1)} s  slowest {round(n.get('max_ms', 0) / 1000, 1)} s")
    return out


def save_run(path: str, did: str, topic: str, turns: list[dict[str, Any]], result: Optional[dict[str, Any]]) -> None:
    """Write the whole debate (every turn in full, plus the stored verdict) to a file: .md for reading, anything else is JSON."""
    if path.endswith(".md"):
        out = [f"# {(result or {}).get('proposition') or topic}", f"\nDebate id: {did}\n"]
        for t in turns:
            out.append(f"\n## {str(t.get('side')).upper()} | {t.get('phase')} {t.get('round')}" + (" (cut short)" if t.get("truncated") else ""))
            for n in t.get("thinking") or []:
                out.append(f"*thinking: {n}*")
            out.append("\n" + (t.get("argument") or ""))
        if result:
            out.append("\n## Verdict\n")
            out.append(f"Winner: {result.get('winner')}  confidence {result.get('confidence')}\n")
            out.append(result.get("summary") or "")
            out.append("\n" + (result.get("final_output") or ""))
            out.append("\n```json\n" + json.dumps(result.get("scores"), indent=1) + "\n```")
            out.append("\n## Cost, tokens and time\n")
            out += ["    " + line for line in usage_lines(result)]
            out.append("\n```json\n" + json.dumps({"usage_summary": result.get("usage_summary"), "timing_summary": result.get("timing_summary"),
                                                  "cost_usd": result.get("cost_usd"), "wall_ms": result.get("wall_ms"),
                                                  "active_ms": result.get("active_ms"), "waited_ms": result.get("waited_ms")}, indent=1) + "\n```")
        text = "\n".join(out)
    else:
        text = json.dumps({"debate_id": did, "topic": topic, "turns": turns, "result": result}, indent=1, default=str)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"Saved the full debate to {path}")


def fetch_result(c: httpx.Client, base: str, headers: dict[str, str], node_id: str) -> Optional[dict[str, Any]]:
    r = c.get(f"{base}/debates/node/{node_id}", headers=headers)
    return r.json() if r.status_code == 200 else None


def print_result(c: httpx.Client, base: str, headers: dict[str, str], node_id: str, v: Optional[dict[str, Any]] = None) -> None:
    if v is None:
        r = c.get(f"{base}/debates/node/{node_id}", headers=headers)
        if r.status_code != 200:
            print(f"\n(could not load the stored result: {r.status_code} {r.text[:200]})")
            return
        v = r.json()
    print("\n" + "=" * 70)
    print(f"Proposition : {v.get('proposition')}")
    sc = v.get("scores") or {}
    rub = sc.get("rubric") or {}
    print(f"Winner      : {v.get('winner')}   confidence {v.get('confidence')}   totals FOR {sc.get('for')} / AGAINST {sc.get('against')}")
    for side in ("for", "against"):
        c = (rub.get("criteria") or {}).get(side)
        if c:
            n = (rub.get("claim_counts") or {}).get(side) or {}
            print(f"  {side.upper():8} evidence {c['evidence']:.1f} scope {c['scope']:.0f} engagement {c['engagement']:.0f} fidelity {c['fidelity']:.0f}   claims: {n}")
            print(f"           {(rub.get('notes') or {}).get(side, '')}")
    if rub:
        print(f"  lead {rub.get('gap')} (needs {rub.get('margin')}), claim coverage {rub.get('coverage')}, verified citations {rub.get('verified_share')}")
        if rub.get("judge_samples"):
            print(f"  judge ran {rub['judge_samples']}x, agreement {rub.get('agreement')}", end="")
            if rub.get("prose_conclusion"):
                flag = "" if rub.get("prose_matches_winner") else ("  (CONTRADICTS the totals)" if rub.get("prose_contradicts_winner") else "  (no conclusion of its own)")
                print(f", written verdict reads as {rub['prose_conclusion']}{flag}", end="")
            print()
    print(f"Judge       : {v.get('judge_model')}")
    print(f"\nSummary: {v.get('summary')}")
    for k, title in (("strongest_counterpoints", "Strongest counterpoints"), ("verdict_flips_if", "Verdict flips if")):
        if v.get(k):
            print(f"\n{title}:")
            for x in v[k]:
                print(f"  - {x}")
    branches = v.get("branches") or []
    if branches:
        kind_word = {"research": "find evidence", "debate": "worth its own debate", "open": "a judgement call"}
        print("\nWhere to go next (tick these to spawn sibling nodes under the node this debate started from):")
        for b in branches:
            mark = "x" if b.get("selected") else " "
            made = f"  -> node {b['created_node_id']}" if b.get("created_node_id") else ""
            print(f"  [{mark}] {b['id']}  {b['title']}  ({kind_word.get(b.get('kind'), b.get('kind'))}){made}")
            print(f"        {b['question']}")
            print(f"        why: {b['why']}")
        print(f"\n  Tick:   curl -X PATCH $API/debates/node/{node_id}/branches -H \"Authorization: Bearer $TOKEN\" "
              f"-H 'content-type: application/json' -d '{{\"selected\":[\"b1\",\"b2\"]}}'")
        print(f"  Create: curl -X POST  $API/debates/node/{node_id}/branches -H \"Authorization: Bearer $TOKEN\" "
              f"-H 'content-type: application/json' -d '{{\"ids\":[\"b1\",\"b2\"]}}'")
    print(f"\nCitations stored: {len(v.get('citations') or [])}   result node: {node_id}")
    print()
    for line in usage_lines(v):
        print(line)


# ----------------------------------------------------------------------- main
def get_token(a: argparse.Namespace) -> str:
    tok = a.token or os.environ.get("DEBATE_TOKEN")
    if tok:
        return tok
    if a.user_id:
        sys.path.insert(0, os.getcwd())
        try:
            from app.auth import create_access_token  # type: ignore
        except Exception as e:  # noqa: BLE001
            sys.exit(f"Could not import app.auth to mint a token ({type(e).__name__}). Run from backend/ with the venv active, or pass --token.")
        return create_access_token({"sub": a.user_id, "type": "access"})
    sys.exit("Need --user-id (to mint a token), or --token / $DEBATE_TOKEN.")


def run(a: argparse.Namespace, read: Callable[[str], str] = input) -> int:
    base = a.base_url.rstrip("/")
    headers = {"Authorization": f"Bearer {get_token(a)}"}
    with httpx.Client(timeout=httpx.Timeout(30.0, read=None)) as c:
        if a.resume:
            did = a.resume
        else:
            for need in ("project", "node", "topic"):
                if not getattr(a, need):
                    sys.exit(f"--{need} is required to start a debate (or use --resume).")
            r = c.post(f"{base}/debates", headers=headers, json={
                "project_id": a.project, "node_id": a.node, "topic": a.topic, "models": a.model, "rounds": a.rounds,
            })
            if r.status_code >= 300:
                sys.exit(f"Could not start the debate: {r.status_code} {r.text[:300]}")
            did = r.json()["id"]
            print(f"Started debate {did}")
        print(f"(if this terminal closes, continue with:  --resume {did})")

        last_id = a.after
        live = Live(enabled=False if getattr(a, "no_stream", False) else None)
        live.start()
        turns: list[dict[str, Any]] = []
        answered: set[str] = set()
        retries = 0
        while True:
            h = dict(headers)
            if last_id:
                h["Last-Event-ID"] = str(last_id)
            try:
                with c.stream("GET", f"{base}/debates/{did}/events", headers=h) as resp:
                    if resp.status_code != 200:
                        sys.exit(f"Could not open the event stream: {resp.status_code} {resp.read().decode()[:200]}")
                    retries = 0
                    for ev in parse_sse(resp.iter_lines()):
                        if ev["id"]:
                            last_id = ev["id"]
                        if ev["event"] == "state":
                            st = ev["data"]
                            print(f"Status: {st.get('status')}  phase: {st.get('current_phase')}  topic: {st.get('topic')}")
                            pq = st.get("pending_questions")
                            if pq and st.get("status") == "awaiting_input":
                                if not answer(c, base, headers, did, pq, a.auto_answer, answered, read):
                                    live.stop()
                                    return 1
                            continue
                        kind = ev["event"]
                        payload = ev["data"].get("payload", {}) if isinstance(ev["data"], dict) else {}
                        if kind == "token":
                            live.token(payload)
                            continue
                        if kind == "thinking":
                            live.note(payload.get("side"), payload.get("text"))
                        if kind in ("question_requested", "done", "failed", "cancelled"):
                            live.drain()  # nothing may still be "speaking" while we ask, or finish
                        if kind == "turn_completed":
                            live.turn_done(payload.get("turn_id"), payload.get("argument"), lambda e=ev: show(e, a.verbose))
                            turns.append(payload)
                        elif kind == "verdict_ready":
                            live.turn_done(payload.get("turn_id"), payload.get("final_output"), lambda: None)
                        else:
                            live.after(lambda e=ev: show(e, a.verbose))
                        if kind == "question_requested":
                            with live.lock:
                                live.erase()
                                ok = answer(c, base, headers, did, payload["questions"], a.auto_answer, answered, read)
                            if not ok:
                                live.stop()
                                return 1
                        elif kind == "done":
                            live.stop()
                            st = ev["data"]
                            print(f"\nFinished: {st.get('status')} ({st.get('end_reason')}), {round((st.get('wall_ms') or 0) / 1000)} s wall time")
                            res = fetch_result(c, base, headers, st["result_node_id"]) if st.get("result_node_id") else None
                            if res:
                                print_result(c, base, headers, st["result_node_id"], res)
                            if a.save:
                                save_run(a.save, did, st.get("topic") or a.topic or "", turns, res)
                            if not res and st.get("error_code"):
                                print(f"Error code: {st['error_code']}")
                            return 0 if st.get("status") == "completed" else 1
            except (httpx.ReadError, httpx.RemoteProtocolError, httpx.ConnectError) as e:
                retries += 1
                if retries > 5:
                    sys.exit(f"Lost the connection too many times ({type(e).__name__}).")
                print(f"(connection dropped, reconnecting {retries}/5)")
                time.sleep(2)
            except KeyboardInterrupt:
                live.stop()
                print(f"\nStopped watching. The debate keeps running on the server. Rejoin with:  --resume {did}")
                return 130
            # The stream ended without a 'done' event: reconnect from the last event seen.
            time.sleep(1)


def answer(c: httpx.Client, base: str, headers: dict[str, str], did: str, questions: list[dict[str, Any]],
           auto: bool, answered: set[str], read: Callable[[str], str]) -> bool:
    """Answer the questions the debate is waiting on right now.

    Replayed events can mention questions that were answered long ago, so ask the server what it is
    waiting for instead of trusting the event. Returns False only on a real failure.
    """
    pending: list[dict[str, Any]] = []
    for _ in range(8):
        r = c.get(f"{base}/debates/{did}", headers=headers)
        if r.status_code == 200 and r.json().get("status") == "awaiting_input" and r.json().get("pending_questions"):
            pending = r.json()["pending_questions"]
            break
        if r.status_code == 200 and r.json().get("status") in TERMINAL:
            return True
        time.sleep(0.5)
    if not pending:
        return True  # stale question from a replay; nothing is waiting
    key = ",".join(sorted(q["id"] for q in pending))
    if key in answered:
        return True
    ans = ask_questions(pending, auto, read)
    body = {"skip": True} if ans is None else {"answers": ans}
    r = c.post(f"{base}/debates/{did}/answer", headers=headers, json=body)
    if r.status_code == 409:
        print("(those questions were already answered)")
        return True
    if r.status_code >= 300:
        print(f"Could not submit the answer: {r.status_code} {r.text[:300]}")
        return False
    answered.add(key)
    print("(answer sent)")
    return True


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--base-url", default=os.environ.get("DEBATE_BASE_URL", "http://127.0.0.1:8000"))
    p.add_argument("--token")
    p.add_argument("--user-id")
    p.add_argument("--project")
    p.add_argument("--node")
    p.add_argument("--topic")
    p.add_argument("--model", action="append", default=None, help="repeat once for two models (sides are assigned at random)")
    p.add_argument("--rounds", type=int, default=2, choices=[1, 2, 3])
    p.add_argument("--resume", metavar="DEBATE_ID")
    p.add_argument("--after", type=int, default=None, help="only show events after this event id (with --resume)")
    p.add_argument("--auto-answer", action="store_true", help="answer every question with its first option")
    p.add_argument("--save", metavar="FILE", help="write the whole debate to FILE at the end (.md to read, anything else for JSON)")
    p.add_argument("--no-stream", action="store_true", help="do not draw the live FOR / AGAINST / judge boxes")
    p.add_argument("--verbose", action="store_true", help="show full arguments and thinking notes")
    return p


def main(argv: Optional[list[str]] = None) -> int:
    a = build_parser().parse_args(argv)
    a.model = a.model or [DEFAULT_MODEL]
    return run(a)


if __name__ == "__main__":
    sys.exit(main())
