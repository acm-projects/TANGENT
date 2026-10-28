import io
import json
import sys
from pathlib import Path

import httpx

from debate.fakes import ScriptedBrain, make_deps
from debate.openrouter import OpenRouterBrain, OpenRouterClient
from debate.streaming import FieldStreamer, FieldTap, StreamSink
from helpers import drive, run
from test_openrouter import ctx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import debate_client as dc  # noqa: E402


def read_all(raw, step, field="argument"):
    f, out = FieldStreamer(field), ""
    for i in range(0, len(raw), step):
        out += f.feed(raw[i:i + step])
    return out


# ------------------------------------------------------------ the JSON field reader
def test_field_streamer_decodes_text_however_the_json_is_chopped_up():
    obj = {"thinking": ["a \"x\" b", "argument"], "argument": 'Hello "q"\nTwo é \U0001F600 end\\ ok — done',
           "claims": [{"text": "argument", "argument": "NOT THIS ONE"}], "argument2": "nor this"}
    for ascii_only in (False, True):  # ascii_only gives \uXXXX escapes and surrogate pairs
        raw = json.dumps(obj, ensure_ascii=ascii_only)
        for step in (1, 2, 3, 5, 7, 1000):
            assert read_all(raw, step) == obj["argument"], (ascii_only, step)


def test_field_streamer_ignores_missing_and_non_string_fields_and_stops_after_the_close():
    assert read_all('{"query": "x", "thinking": "y"}', 3) == ""
    assert read_all('{"argument": null, "z": "q"}', 3) == ""
    assert read_all('{"argument": ["a"], "z": "q"}', 3) == ""
    f = FieldStreamer("final_output")
    assert f.feed('{"a": 1, "final_output": "one"') == "one" and f.done
    assert f.feed(', "x": "more"}') == ""


# ------------------------------------------------------------ batching into events
class Clock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


def make_sink(**kw):
    sent, clock = [], Clock()

    async def emit(payload, key):
        sent.append((payload, key))

    return StreamSink(emit, {"turn_id": "t1", "side": "for", "phase": "opening", "round": 0}, clock=clock, background=False, **kw), sent, clock


def test_sink_sends_first_text_at_once_then_batches_by_time():
    sink, sent, clock = make_sink(interval_s=0.25, max_chars=1000)

    async def go():
        await sink.start()
        await sink.push("Hel")        # first text goes out immediately
        await sink.push("lo ")        # buffered
        clock.t += 0.1
        await sink.push("wor")        # still inside the interval
        clock.t += 0.3
        await sink.push("ld")         # interval passed: flush
        await sink.push("!")          # buffered again
        await sink.close()            # the rest goes at close
    run(go())
    assert [p["text"] for p, _ in sent] == ["Hel", "lo world", "!"]
    assert [p["seq"] for p, _ in sent] == [1, 2, 3]
    assert len({k for _, k in sent}) == 3
    assert all(p["turn_id"] == "t1" and p["side"] == "for" and p["attempt"] == 1 for p, _ in sent)


def test_sink_flushes_early_when_a_lot_of_text_piles_up():
    sink, sent, _ = make_sink(interval_s=60, max_chars=10)

    async def go():
        await sink.start()
        await sink.push("a")
        await sink.push("b" * 12)
    run(go())
    assert [p["text"] for p, _ in sent] == ["a", "b" * 12]


def test_retry_after_streamed_text_sends_a_reset_and_a_new_attempt():
    sink, sent, _ = make_sink()

    async def go():
        await sink.start()
        await sink.push("first try")
        await sink.start()                      # the model call was retried
        await sink.push("second try")
        await sink.close()
    run(go())
    assert [(p["attempt"], p["text"], p.get("reset")) for p, _ in sent] == [
        (1, "first try", None), (2, "", True), (2, "second try", None)]
    assert len({k for _, k in sent}) == 3


def test_sink_with_nothing_streamed_sends_nothing_and_a_failing_emit_is_swallowed():
    sink, sent, _ = make_sink()
    run(sink.start())
    run(sink.close())
    assert sent == []

    async def boom(payload, key):
        raise RuntimeError("db down")
    bad = StreamSink(boom, {"turn_id": "t"}, background=False)

    async def go():
        await bad.start()
        await bad.push("text")
        await bad.close()
    run(go())  # must not raise


def test_a_slow_database_never_holds_up_the_text_and_everything_is_written_in_order_by_close():
    import asyncio
    written, gate = [], asyncio.Event()

    async def slow_emit(payload, key):
        await gate.wait()                       # the database is "slow": nothing is written until the gate opens
        written.append(payload["text"])

    sink = StreamSink(slow_emit, {"turn_id": "t"}, interval_s=0, max_chars=1)

    async def go():
        await sink.start()
        for word in ("a", "b", "c", "d"):
            await asyncio.wait_for(sink.push(word), timeout=1)   # would hang here if pushing waited for the database
        assert written == []
        gate.set()
        await sink.close()                       # waits for the queue to be written
    run(go())
    assert "".join(written) == "abcd" and len(written) <= 2   # pieces that piled up behind the slow write went out merged


def test_a_database_write_slower_than_the_flush_interval_does_not_slow_the_model_stream():
    """The bug this guards against: when one write took longer than the flush interval, every incoming piece triggered
    its own write and the model stream stalled behind them (a 2 s answer took 30 s)."""
    import asyncio
    import time
    writes = []

    async def slow_emit(payload, key):
        await asyncio.sleep(0.3)                # a database round trip longer than the 0.25 s flush interval
        writes.append(payload["text"])

    sink = StreamSink(slow_emit, {"turn_id": "t"})

    async def go():
        t0 = time.monotonic()
        await sink.start()
        for _ in range(60):
            await asyncio.sleep(0.01)            # the model emits a small piece every 10 ms (0.6 s in all)
            await sink.push("ab")
        streamed_in = time.monotonic() - t0
        await sink.close()
        return streamed_in, time.monotonic() - t0
    streamed_in, finished_in = run(go())
    assert streamed_in < 1.2                     # the old code took about 18 s here
    assert finished_in < 2.5                     # and the end of the turn does not wait for a long backlog
    assert "".join(writes) == "ab" * 60 and len(writes) <= 6


# ------------------------------------------------------------ the OpenRouter stream
def sse_body(chunks):
    return "".join(f"data: {json.dumps(c)}\n\n" for c in chunks) + "data: [DONE]\n\n"


def tool_stream(args, usage=True):
    pieces = [args[i:i + 9] for i in range(0, len(args), 9)]
    out = [{"id": "gen-s", "model": "x/for", "choices": [{"delta": {"role": "assistant", "content": ""}}]}]
    out.append({"id": "gen-s", "choices": [{"delta": {"tool_calls": [{"index": 0, "id": "t1", "type": "function",
                                                                       "function": {"name": "submit_turn", "arguments": pieces[0]}}]}}]})
    for p in pieces[1:]:
        out.append({"id": "gen-s", "choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": p}}]}}]})
    out.append({"id": "gen-s", "choices": [{"delta": {}, "finish_reason": "tool_calls"}]})
    if usage:
        out.append({"id": "gen-s", "model": "x/for", "choices": [],
                    "usage": {"prompt_tokens": 50, "completion_tokens": 12, "cost": 0.001,
                              "completion_tokens_details": {"reasoning_tokens": 2}, "prompt_tokens_details": {"cached_tokens": 5}}})
    return out


class StreamServer:
    def __init__(self, *replies):
        self.replies = list(replies)
        self.requests = []

    def __call__(self, request):
        self.requests.append(json.loads(request.content))
        r = self.replies.pop(0)
        if isinstance(r, int):
            return httpx.Response(r, json={"error": {"message": "x"}})
        return httpx.Response(200, content=r.encode(), headers={"content-type": "text/event-stream"})


def stream_brain(server):
    async def nosleep(_):
        return None
    http = httpx.AsyncClient(transport=httpx.MockTransport(server))
    client = OpenRouterClient("sk-test", http=http, sleep=nosleep)
    return OpenRouterBrain(client, for_model="x/for", against_model="x/against", judge_model="x/judge")


TURN = {"thinking": ["note one"], "argument": "Alpha wins.\nSecond \"line\".", "claims": [{"text": "c", "evidence_ids": []}]}


def test_debater_turn_streams_the_argument_and_still_returns_the_normal_action():
    server = StreamServer(sse_body(tool_stream(json.dumps(TURN))))
    sink, sent, _ = make_sink(interval_s=0)
    action = run(stream_brain(server).step(ctx(phase="opening", may_search=False, may_ask=False), sink))
    run(sink.close())
    assert server.requests[0]["stream"] is True
    assert "".join(p["text"] for p, _ in sent) == TURN["argument"]
    assert action.kind == "finish" and action.turn.argument == TURN["argument"]
    assert action.usage.prompt_tokens == 50 and action.usage.cost == 0.001 and action.usage.reasoning_tokens == 2


def test_a_search_call_streams_nothing_and_a_503_is_retried_with_the_text_cleared():
    search = tool_stream(json.dumps({"query": "q", "thinking": "t"}))
    for ch in search:
        for tc in (ch.get("choices") or [{}])[0].get("delta", {}).get("tool_calls", []):
            if tc.get("function", {}).get("name"):
                tc["function"]["name"] = "search_papers"
    server = StreamServer(503, sse_body(search))
    sink, sent, _ = make_sink(interval_s=0)
    action = run(stream_brain(server).step(ctx(), sink))
    assert action.kind == "search" and action.query == "q"
    assert sent == [] and len(server.requests) == 2


def test_a_stream_that_dies_halfway_is_retried_and_the_client_is_told_to_clear_the_text():
    good = sse_body(tool_stream(json.dumps(TURN)))
    cut = good[: good.index("finish_reason") - 40]  # the connection ends in the middle of the argument, with no [DONE]
    server = StreamServer(cut, good)
    sink, sent, _ = make_sink(interval_s=0)
    action = run(stream_brain(server).step(ctx(phase="opening", may_search=False, may_ask=False), sink))
    run(sink.close())
    assert action.kind == "finish"
    resets = [p for p, _ in sent if p.get("reset")]
    assert len(resets) == 1 and resets[0]["attempt"] == 2
    final = "".join(p["text"] for p, _ in sent if p["attempt"] == 2)
    assert final == TURN["argument"]


def test_judge_final_output_streams_from_the_message_text():
    verdict = {"claim_checks": [], "criteria": [], "leaning": "none", "rationale": "r", "summary": "s",
               "final_output": "The evidence is mixed.\nSee below.", "strongest_counterpoints": [], "verdict_flips_if": []}
    raw = json.dumps(verdict)
    pieces = [raw[i:i + 11] for i in range(0, len(raw), 11)]
    chunks = [{"id": "g", "choices": [{"delta": {"content": p}}]} for p in pieces]
    chunks.append({"id": "g", "choices": [{"delta": {}, "finish_reason": "stop"}]})
    chunks.append({"id": "g", "choices": [], "usage": {"prompt_tokens": 5, "completion_tokens": 5}})
    server = StreamServer(sse_body(chunks))
    sink, sent, _ = make_sink(interval_s=0)
    from debate.deps import JudgeView
    v = run(stream_brain(server).judge(JudgeView(rendered="x", labels=["A", "B"], cited_evidence={}), None, sink))
    run(sink.close())
    assert "".join(p["text"] for p, _ in sent) == verdict["final_output"]
    assert v.final_output == verdict["final_output"]


# ------------------------------------------------------------ a whole fake debate
def test_every_turn_and_the_judge_stream_and_the_pieces_add_up_to_the_finished_text():
    deps = make_deps(ScriptedBrain(), stream_tokens=True)
    run(drive(deps, rounds=1))
    tokens = deps.emitter.of("token")
    done = deps.emitter.of("turn_completed")
    assert tokens and done
    by_turn = {}
    for t in tokens:
        by_turn.setdefault(t["turn_id"], []).append(t)
    for turn in done:
        assert turn["turn_id"] in by_turn, "every finished turn was streamed"
        pieces = by_turn[turn["turn_id"]]
        assert {p["side"] for p in pieces} == {turn["side"]}
        assert "".join(p["text"] for p in pieces if not p.get("reset")) == turn["argument"]
    judge = [t for t in tokens if t["side"] == "judge"]
    assert judge and "".join(t["text"] for t in judge) == "final output text"
    ready = deps.emitter.of("verdict_ready")
    assert len(ready) == 1 and ready[0]["turn_id"] == judge[0]["turn_id"] and ready[0]["final_output"]


def test_streaming_is_off_by_default():
    deps = make_deps(ScriptedBrain())
    run(drive(deps, rounds=1))
    assert deps.emitter.of("token") == [] and deps.emitter.of("turn_completed")


# ------------------------------------------------------------ the terminal stage
class Tick:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def stage(**kw):
    clock = Tick()
    live = dc.Live(io.StringIO(), enabled=True, width=70, rows=24, max_lines=4, clock=clock, **kw)

    def advance(n=1, dt=0.1):
        for _ in range(n):
            clock.t += dt
            live.tick()
    return live, advance


def tok(tid, side, text, **kw):
    return {"turn_id": tid, "side": side, "phase": "opening", "round": 0, "text": text, **kw}


FOR_TEXT = "FOR says alpha is better. " * 6
AGAINST_TEXT = "AGAINST says beta is better. " * 6


def test_only_one_debater_speaks_at_a_time_and_the_other_waits_with_its_text_ready():
    live, advance = stage()
    live.token(tok("F", "for", FOR_TEXT[:60]))
    live.token(tok("A", "against", AGAINST_TEXT))      # arrives second, in parallel
    live.token(tok("F", "for", FOR_TEXT[60:]))
    advance(2)
    frame = "\n".join(live.frame())
    assert "FOR | opening 0 is speaking" in frame and "next: AGAINST (%d chars ready)" % len(AGAINST_TEXT) in frame
    assert "AGAINST says" not in frame.split("\n", 1)[1]          # none of the waiting side's words are on screen


def test_the_waiting_debater_speaks_after_the_first_and_summaries_print_in_speaking_order():
    live, advance = stage()
    log = []
    live.token(tok("F", "for", FOR_TEXT))
    live.token(tok("A", "against", AGAINST_TEXT))
    live.turn_done("A", AGAINST_TEXT, lambda: log.append("against summary"))   # AGAINST finished first on the server
    live.after(lambda: log.append("next phase header"))
    advance(2)
    assert log == []                                           # nothing prints while FOR is still speaking
    live.turn_done("F", FOR_TEXT, lambda: log.append("for summary"))
    advance(6)
    assert log == ["for summary"]                              # AGAINST has not been spoken yet, so its summary waits
    advance(6)
    assert log[:2] == ["for summary", "against summary"]
    advance(30)
    assert log == ["for summary", "against summary", "next phase header"] and live.order == []


def test_text_is_not_shown_faster_than_the_typing_speed_and_catches_up_on_a_big_backlog():
    live, advance = stage()
    live.token(tok("F", "for", "x" * 400))
    live.turn_done("F", "x" * 400, lambda: None)
    advance(1, dt=0.1)                                           # 0.1 s at 400 chars/s = 40 characters
    assert 30 <= live.turns["F"]["shown"] <= 50
    live2, advance2 = stage()
    live2.token(tok("F", "for", "y" * 5000))
    live2.turn_done("F", "y" * 5000, lambda: None)
    advance2(1, dt=0.1)
    assert live2.turns["F"]["shown"] >= 100                    # big backlog: 1500 chars/s


def test_reset_clears_the_text_and_a_finished_turn_is_never_replayed():
    live, advance = stage()
    live.token(tok("F", "for", "first try text"))
    live.token(tok("F", "for", "", reset=True))
    live.token(tok("F", "for", "second"))
    assert live.turns["F"]["got"] == "second"
    live.turn_done("F", "second", lambda: None)
    advance(10)
    live.token(tok("F", "for", "late replay"))
    assert "F" not in live.turns


def test_both_debaters_thinking_notes_show_at_the_same_time():
    live, _ = stage()
    live.token(tok("F", "for", "speaking"))
    live.note("for", "checking the call-centre study")
    live.note("against", "looking for a meta-analysis")
    frame = "\n".join(live.frame())
    assert "FOR     thinking: checking the call-centre study" in frame
    assert "AGAINST thinking: looking for a meta-analysis" in frame


def test_drain_prints_everything_waiting_in_order_without_the_animation():
    live, _ = stage()
    log = []
    live.token(tok("F", "for", FOR_TEXT))
    live.token(tok("A", "against", AGAINST_TEXT))
    live.turn_done("F", FOR_TEXT, lambda: log.append("for"))
    live.after(lambda: log.append("barrier"))
    live.drain()
    assert log == ["for", "barrier"] and live.order == [] and live.turns == {}


def test_the_stage_always_fits_the_screen_even_in_a_short_window():
    clock = Tick()
    live = dc.Live(io.StringIO(), enabled=True, width=60, rows=12, max_lines=12, clock=clock)
    live.token(tok("F", "for", "word " * 500))
    live.note("for", "n1")
    live.note("against", "n2")
    clock.t += 5
    live.tick()
    assert len(live.frame()) <= 12 - 3


def test_nothing_is_drawn_and_everything_prints_at_once_when_not_a_terminal():
    plain = io.StringIO()
    off = dc.Live(plain)                      # StringIO is not a tty
    log = []
    off.token(tok("F", "for", "x"))
    off.turn_done("F", "x", lambda: log.append("summary"))
    off.after(lambda: log.append("later"))
    off.tick()
    assert log == ["summary", "later"] and plain.getvalue() == "" and off.frame() == []
