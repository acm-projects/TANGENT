"""Read-only scorecard for one agent run. Never starts a run, never touches the database.

    curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/projects/<pid>/agent/runs/<rid>/trace > trace.json
    python scripts/agent_scorecard.py trace.json [--json]

Prints the objective numbers of docs/agent_eval_log.md. The process-showcase checks (P1-P8) and claim truth are read by a human.
"""
import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime

READ_ONLY = {"get_node", "search_nodes", "search_sources", "search_papers", "get_paper", "search_paper_evidence", "web_search"}
SEARCHES = READ_ONLY - {"get_node", "search_nodes"}
LIMITS = {"steps": 60, "tool_calls": 60}


def _t(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value


def _norm(args: dict) -> str:
    q = args.get("query") or args.get("q") or json.dumps(args, sort_keys=True)
    return re.sub(r"\W+", " ", str(q).lower()).strip()


def score(trace: dict) -> dict:
    ex, events, calls = trace["executions"], trace["events"], trace["llm_calls"]
    tools = [e for e in ex if e["kind"] == "tool"]
    ops = [e for e in ex if e["kind"] == "op"]
    ok_reads = [e for e in tools if e["status"] == "succeeded" and e["name"] in READ_ONLY]
    out: dict = {}

    out["status"] = next((e["type"].split(".")[1] for e in reversed(events) if e["type"] in
                          ("run.completed", "run.failed", "run.cancelled")), "not finished")
    fin = next((e for e in reversed(ops) if e["name"] == "finish_research" and e["status"] == "succeeded"), None)
    fa = fin["args"] if fin else {}
    out["outcome"] = fa.get("outcome")
    out["steps"] = f"{max((e['iteration'] for e in ex), default=0)}/{LIMITS['steps']}"
    out["tool_calls"] = f"{len(tools)}/{LIMITS['tool_calls']}"
    if events:
        out["wall_minutes"] = round((_t(events[-1]["created_at"]) - _t(events[0]["created_at"])).total_seconds() / 60, 1)
    tokens = [(c.get("usage") or {}) for c in calls]
    out["tokens"] = sum(u.get("total_tokens") or (u.get("prompt_tokens", 0) + u.get("completion_tokens", 0)) for u in tokens)
    out["llm_retries"] = sum(1 for c in calls if c["attempt"] > 1)
    out["rejected_steps"] = dict(Counter(str((e["result"] or {}).get("error", ""))[:70] for e in ops + tools
                                         if e["kind"] == "op" and e["status"] == "failed"))

    ws = [e for e in tools if e["name"] == "web_search"]
    out["web_search_failed"] = f"{sum(e['status'] != 'succeeded' or 'error' in (e['result'] or {}) for e in ws)}/{len(ws)}"
    per_task = Counter(e["task_key"] for e in tools if e["name"] in SEARCHES)
    out["searches_per_task"] = dict(per_task)
    queries = Counter(_norm(e["args"]) for e in tools if e["name"] in SEARCHES)
    out["duplicate_queries"] = {q: n for q, n in queries.items() if n > 1}

    # evidence the finish cites that no successful read result contains (nodes the agent wrote never count)
    blob = " ".join(json.dumps(e["result"], default=str) for e in ok_reads).lower()
    out["evidence_not_retrieved"] = [r for r in fa.get("evidence", []) if r.lower().rstrip("/") not in blob]

    unresolved = [u for e in ops if e["name"] == "complete_task" and e["status"] == "succeeded" for u in e["args"].get("unresolved", [])]
    out["satisfied_with_unresolved"] = out["outcome"] == "satisfied" and bool(unresolved or fa.get("unresolved_questions"))

    made = {}  # node id -> (title, has_body)
    parents = set()
    for e in tools:
        if e["status"] != "succeeded" or e["name"] not in ("write_node", "branch_node"):
            continue
        nid = (e["result"] or {}).get("node_id")
        parents.add(str(e["args"].get("parent_id") or e["args"].get("node_id")))
        made[nid] = (e["args"].get("title"), bool(str(e["args"].get("body", "")).strip()))
    out["nodes_written"] = len(made)
    out["empty_leaves"] = [t for n, (t, body) in made.items() if not body and n not in parents]
    out["replans"] = sum(1 for e in events if e["type"] == "plan.revised")
    out["delete_without_confirmation"] = [e["args"] for e in tools if e["name"] == "delete_node" and e["status"] == "succeeded"
                                          and not any(ev["type"] == "input.answered" for ev in events)]
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("trace")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    with open(a.trace, encoding="utf-8") as f:
        card = score(json.load(f))
    if a.json:
        json.dump(card, sys.stdout, indent=2)
    else:
        for k, v in card.items():
            print(f"{k:28} {v}")
