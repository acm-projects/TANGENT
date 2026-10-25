import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from scripts import debate_client  as dc  # noqa: E402


def test_parse_sse_skips_pings_and_reads_frames():
    lines = [": ping", "id: 3", "event: thinking", 'data: {"payload": {"text": "hi"}}', "", ": ping", "event: done", 'data: {"id": "x"}', ""]
    evs = list(dc.parse_sse(iter(lines)))
    assert [e["event"] for e in evs] == ["thinking", "done"]
    assert evs[0]["id"] == "3" and evs[0]["data"]["payload"]["text"] == "hi"


def test_ask_questions_single_multi_other_and_skip():
    q = [{"id": "a", "prompt": "p", "type": "single", "options": [{"label": "X"}, {"label": "Y"}], "allow_other": True},
         {"id": "b", "prompt": "m", "type": "multi", "options": [{"label": "P"}, {"label": "Q"}], "allow_other": True}]
    replies = iter(["9", "2", "1,2"])
    assert dc.ask_questions(q, False, lambda _: next(replies)) == {"a": "Y", "b": ["P", "Q"]}
    assert dc.ask_questions(q, False, lambda _: "my own") ["a"] == "my own"
    assert dc.ask_questions(q, False, lambda _: "skip") is None
    assert dc.ask_questions(q, True) == {"a": "X", "b": ["P"]}


class Fake(BaseHTTPRequestHandler):
    state = {"status": "running", "answers": None}

    def log_message(self, *a):
        pass

    def _json(self, code, obj):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}")
        if self.path == "/debates":
            return self._json(202, {"id": "d1", "status": "queued"})
        if self.path == "/debates/d1/answer":
            if Fake.state["status"] != "awaiting_input":
                return self._json(409, {"detail": "not awaiting"})
            Fake.state["answers"] = body
            Fake.state["status"] = "running"
            return self._json(202, {"status": "queued"})
        self._json(404, {})

    def do_GET(self):
        st = Fake.state["status"]
        if self.path == "/debates/d1":
            pq = [{"id": "q1", "prompt": "What does it refer to?", "type": "single", "options": [{"label": "A"}, {"label": "B"}], "allow_other": True}]
            return self._json(200, {"id": "d1", "status": st, "pending_questions": pq if st == "awaiting_input" else None})
        if self.path.startswith("/debates/node/"):
            return self._json(200, {"proposition": "P?", "winner": "for", "confidence": 0.7, "scores": {"for": 6, "against": 5},
                                    "judge_model": "j", "summary": "S", "final_output": "Final answer text.", "cost_usd": 0.0421, "wall_ms": 90000, "active_ms": 88000, "waited_ms": 2000,
                                    "usage_summary": {"total": {"calls": 3, "attempts": 4, "cost": 0.0421, "prompt_tokens": 1000, "completion_tokens": 500, "reasoning_tokens": 100, "cached_tokens": 50, "total_tokens": 1500},
                                                      "by_role": {"judge": {"calls": 1, "cost": 0.01, "prompt_tokens": 600, "completion_tokens": 200, "latency_ms": 4000}}},
                                    "timing_summary": {"phases": {"opening:0": {"seconds": 12.5}}, "by_node": {"judge": {"count": 1, "total_ms": 4000, "max_ms": 4000}}}, "strongest_counterpoints": ["c"], "verdict_flips_if": ["f"], "citations": []})
        if self.path == "/debates/d1/events":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            w = lambda s: (self.wfile.write(s.encode()), self.wfile.flush())
            w('event: state\ndata: {"status": "running", "topic": "t"}\n\n')
            w('id: 1\nevent: phase_changed\ndata: {"payload": {"phase": "intake"}}\n\n')
            Fake.state["status"] = "awaiting_input"
            w('id: 2\nevent: question_requested\ndata: {"payload": {"questions": [{"id": "q1"}]}}\n\n')
            for _ in range(100):
                if Fake.state["answers"] is not None:
                    break
                time.sleep(0.05)
            w('id: 3\nevent: answer_received\ndata: {"payload": {}}\n\n')
            w('id: 4\nevent: turn_completed\ndata: {"payload": {"side": "for", "phase": "opening", "round": 0, "argument": "arg"}}\n\n')
            w('event: done\ndata: {"id": "d1", "status": "completed", "end_reason": "rounds_exhausted", "wall_ms": 1000, "result_node_id": "n1"}\n\n')
            return
        self._json(404, {})


def test_client_full_flow_with_a_question(capsys, tmp_path):
    Fake.state.update(status="running", answers=None)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        a = dc.build_parser().parse_args(["--base-url", f"http://127.0.0.1:{srv.server_port}", "--token", "t",
                                          "--project", "p", "--node", "n", "--topic", "Is it worth it?",
                                          "--save", str(tmp_path / "run.md")])
        a.model = ["m"]
        assert dc.run(a, read=lambda _: "2") == 0
    finally:
        srv.shutdown()
    out = capsys.readouterr().out
    assert "What does it refer to?" in out and "(answer sent)" in out and "Winner      : for" in out
    assert Fake.state["answers"] == {"answers": {"q1": "B"}}
    md = (tmp_path / "run.md").read_text()
    assert "## FOR | opening 0" in md and "arg" in md and "## Verdict" in md and "P?" in md
    assert "Final answer text." in md and "## Cost, tokens and time" in md and "$0.0421" in md and "1,500" in md and "phase opening:0" in md
    assert "Cost        : $0.0421" in out and "90.0 s wall" in out