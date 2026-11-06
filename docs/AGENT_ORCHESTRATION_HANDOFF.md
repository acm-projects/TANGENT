# Agent orchestration: handoff

For the next agent (or person) picking this up. State as of branch `yafi/feature/gent_orchestration`, last commit `43c650b`.
Everything described here is committed; nothing is pushed. Read this first, then `backend/app/agent/ops.py`.

## 1. What this is and why

TANGENT is a research tool whose UI is a **tree of nodes** (project -> tree -> nodes, each node a small chat). The old agent
(`backend/app/agent/router.py`, `POST /projects/{id}/agent`) is a stateless one-shot tool loop: no goal, plan, tasks, events,
pauses, limits or recovery. It is **kept alongside** and untouched (it backs the old test bench; its tests still pass).

The new work is an **orchestration runtime**: a persistent, bounded, LLM-directed loop that can take a research goal and carry it out
without the user driving each step. The design brief (pasted by the user) in one paragraph:

> The LLM makes the research decisions (plan, investigate, evaluate, replan, ask, finish). The backend is deterministic infrastructure:
> it owns run status, limits, validation, execution and persistence. Research state survives LLM calls and restarts. Conclusions must
> reference actual retrieved evidence. One agent, sequential, flat tasks with dependencies, persisted events + SSE, no context
> compaction, no multi-agent, no thesis-specific engine.

Goals the user cares about, in their words/actions: an agent that finishes multi-step research on its own; **a proper tree structure in
the project (not one note with the result)**; honest outcomes (no "satisfied" with open questions); traceability of a whole run;
long response times are expected and acceptable (free OpenRouter models).

## 2. Architecture

```
UI (AgentWindow) --POST /agent/runs--> runs_router --> store.create_run  (status queued)
                 <--SSE /events------- reads agent_events (persist-then-replay, Last-Event-ID)
worker.py (3 asyncio tasks in the API process, papers-worker style)
   claim() queued/stale run (FOR UPDATE SKIP LOCKED) -> loop.run_loop(run_id)
loop.run_loop:  resume_in_flight -> repeat { load_state -> limits? -> begin_iteration -> step }
step:           decide (ONE LLM call, snapshot prompt) -> parse -> guards -> apply op | run tools
```

Files (`backend/app/agent/`; sizes are small, read them all):

| File | Role |
|---|---|
| `schema.py` | DDL for 6 tables (run by `database.ensure_columns` at startup; same SQL in `backend/migrations/2026-11-agent-runs.sql`). No RLS: the router checks `agent_runs.user_id`; tool calls still run under RLS via `tools._session`. |
| `ops.py` | **The rule engine.** The 8 orchestration operations (pydantic arg models + OpenAI tool schemas), limits, and `check(state, name, args, forced=False)`: pure, DB-free. `State` = run + plan + tasks + all executions. Start here. |
| `prompts.py` | System prompt and `snapshot(state)`: the compact state the model sees each step (goal, answers, budget, plan, tasks, completed findings, nodes written, recent steps). The whole tree is never injected. |
| `store.py` | All SQL. Only this module changes run status/plan/tasks. `apply_op` applies an accepted op + events + execution record in one txn. Also claim, answer, cancel, fail, limits wrap-up, reads for the API. |
| `loop.py` | `decide` (LLM call, 3 attempts, logs every attempt to `agent_llm_calls`), `step`, `wrap_up` (forced `finish_research` when a limit hits), `run_loop`. |
| `executor.py` | Runs research tools via `tools.call_tool` with a write-ahead `agent_executions` row; timeout; one retry for reads; restart recovery (`resume_in_flight`). |
| `worker.py` | Claim/lease (`STALE_SECONDS=300`), 30 s heartbeat, 1 s poll, 3 workers. No cross-loop `asyncio.Event` (it broke across event loops; polling is deliberate). |
| `runs_router.py` | `POST /projects/{id}/agent/runs`, `GET .../{rid}`, `GET .../{rid}/events` (SSE), `POST .../answer`, `POST .../cancel`, `GET .../trace` (developer view). Owner-only; one live run per project (unique index) -> 409. |
| `tools.py` (existing) | Research/graph tools: `get_node, search_nodes, search_sources, search_papers, get_paper, search_paper_evidence, web_search` (read-only) and `branch_node, write_node, merge_nodes, delete_node, ask_node` (writes, owner-only). |

Tables: `agent_runs` (goal immutable, status, outcome, final, pending_input, clarifications, authorized_deletes, counters, lease),
`agent_plans` (versioned), `agent_tasks` (key `t1..`, flat, `depends_on` jsonb, assessment), `agent_executions` (write-ahead ledger of
every op and tool call; the evidence source), `agent_llm_calls` (messages, response, usage, duration per attempt), `agent_events`
(replayable log, `event_key` dedupes).

Statuses: runs `queued | running | waiting_input | completed | failed | cancelled`; outcome `satisfied | partially_satisfied |
inconclusive | blocked`; tasks `pending | in_progress | completed | skipped | failed | blocked | unfinished`
(`unfinished` = the runtime stopped it at a limit after it had made successful calls; `blocked` is set by the runtime when a
dependency failed/was skipped/unfinished, never by the model).

Events: `run.created/started/completed/failed/cancelled`, `run.limit`, `plan.created/revised`, `task.created/started/completed/
skipped/failed/updated`, `tool.executed`, `input.requested/answered`, then a final SSE `done`. **There is no `state` frame**: replaying
from id 0 rebuilds the whole run, which is what the frontend reducer relies on.

## 3. The loop and its rules (all enforced in code, not prompts)

One decision per step: exactly one operation, **or** one write tool, **or** up to 4 independent read-only tools (`ops.batch_error`).
Anything else, plain text, unknown tool, bad JSON, or a rule violation is a *rejected step*: recorded as a failed op execution, returned to
the model as an error, counted. **3 consecutive rejections, or 8 in the whole run, fail the run.**

Guards in `step` order: batch policy -> `ops.needs_task` (no research/write while a plan exists, nothing is in progress and a task could
start) -> `ops.research_capped` (a task gets `MAX_RESEARCH_PER_TASK=6` searches; tree reads `get_node/search_nodes` are free, writes are
never capped) -> `ops.check` for operations -> tool budget -> delete confirmation.

Operation rules (`ops.check`): one plan; `update_plan` needs a reason, max 3; max 12 tasks; `depends_on` must exist; a task starts only
when its deps are completed and nothing else is in progress; re-stating a task's current status is a no-op (other fields still apply);
the model can never set `completed`; `complete_task` needs the task in progress, a successful research call *in that task* (**or** the task
`depends_on` earlier tasks, i.e. it may only synthesise), and every cited node id / source id / URL must have appeared in a successful
tool result of the run (also accepted: the selected node, a bare site or shortened URL of a retrieved URL); `finish_research` needs all
tasks closed, `satisfied` only with no unresolved questions and every completed task satisfied, and (unless `inconclusive` or the run was
forced to finish) at least one successful `write_node` and, if anything was researched, evidence that is a *read* result (nodes the agent
wrote itself never count as final evidence). List args sent as JSON strings are coerced.

Limits (`ops.py`): 60 steps, 60 tool calls, 3 replans, 12 tasks. Below 20% budget the snapshot says `LOW BUDGET`. On exhaustion
`loop.wrap_up`: open tasks become `unfinished`/`skipped`, `run.limit` is emitted, the model gets one forced `finish_research` call
(`ops.check(..., forced=True)` waives the write/evidence demands); if that fails the runtime records an honest fallback.

User input: `request_user_input` (1-3 questions: single/multi/text) pauses the run (`waiting_input`, question persisted, lease released);
`POST /answer` validates every question, appends to `clarifications` (always shown to the model) and requeues. `delete_node` is **refused
by the runtime**, which raises its own confirmation question; only the user's "Delete it" answer authorises that node.

Recovery: tool calls are written before they run. After a restart a stale-locked run is re-claimed; in-flight reads are re-run, in-flight
writes become `unknown` and the snapshot tells the model to inspect the tree before retrying. (Tested in `tests/pg`, **never exercised live**.)

## 4. Frontend

`frontend/src/ui/pages/workspace/features/agent/`: `AgentWindow.tsx/.css` (goal box + model select; then goal, status, plan with
assumptions, task checklist with deps, last 6 tool calls, question card, "Stopped at" banner, final assessment, Cancel/New run),
`useAgentRun.ts`, `agentRunActions.ts` (start/follow/answer/cancel; remembers the run id per project in localStorage; re-reads the tree
once per burst after a successful write), `RunQuestions.tsx` (deliberately a copy of the debate card's logic, because features may not import
each other). State: `store/agentRunStore.ts` (pure idempotent reducer over events, deduped by `lastEventId`). Transport:
`api/stream.ts` (`followEventLog` is the shared reconnecting SSE follower; `streamDebate` and `streamAgentRun` wrap it),
`api/endpoints/agent.ts`, types in `api/types.ts`. The window opens from the robot button next to "Open chat" **while chat is collapsed**.

## 5. Tests and how to run them

- Rule engine and snapshot, no DB, CI-safe: `cd backend && python -m pytest tests/test_agent_ops.py tests/test_agent_runs_api.py -q`
- Whole runtime against real Postgres (scripted model + scripted tools; the acceptance scenario is `test_autonomous_run`):
  needs a scratch Postgres superuser URL: `TEST_PG_ADMIN_URL=postgresql://postgres:@127.0.0.1:PORT/postgres python -m pytest tests/pg/test_agent_runtime.py -q`.
  The file builds its own throwaway database (users, projects, nodes, papers + agent tables). A throwaway server was made with the
  `pgserver` pip package in a temp venv (not a project dependency; it lacks `pgcrypto`, so the older `tests/pg` base schema can't use it).
  That server was in a session scratchpad and is not guaranteed to exist: recreate it or point at any scratch Postgres.
- Frontend: `cd frontend && npx tsc --noEmit && npx vitest run && npx oxlint && npx eslint src` (149 tests at last run).
- Last full run: 57 backend agent tests (rules 35 + runs-api 5 + Postgres scenarios 17), all passing; frontend all passing.
- Pre-existing, not ours: `tests/pg/conftest.py`'s skip marker doesn't match Windows paths (errors without `TEST_PG_ADMIN_URL`);
  `tests/test_search_s2.py::test_requests_are_spaced_by_the_shared_throttle` fails alone on a clean HEAD; many `test_tree_flow`/`test_auth_flow`
  etc. only skip when no `.env` exists (with the repo's `.env` they try the shared RDS and error with connection refused).

## 6. Environment gotchas (these cost time)

- Dev: `npm run dev` from the repo root (api on 8000 via `uvicorn --reload`, web on 5173). **On Windows any edit under `backend/` makes the
  reloader take the whole `concurrently` group down** ("Terminate batch job"). Restart after backend edits; the API needs ~20-40 s before it
  answers (startup talks to the DB).
- The repo-root `.env` (gitignored) points `DATABASE_URL` at the **team's shared RDS**. Running the app creates the `agent_*` tables there
  (`ensure_columns`) and live runs write real nodes into the user's project. The user's test project is "polar bear 67"
  (`/polar-bears/82d5c166-0db2-4368-b5f5-f542ad7b3663`); it still holds test nodes from the runs ("School energy options", "School energy study" subtree).
- Live testing recipe (used with the Playwright MCP, signed in as the user): open the project, click the root node, click "Collapse chat",
  click "Open agent", "New run", type a goal, "Start research". Read progress from the DOM (`.agent-status`, `.agent-task[data-status]`,
  `.agent-activity`) and the full picture from `GET /api/projects/{pid}/agent/runs/{rid}/trace` (get a token with `POST /api/auth/refresh`).
  Individual tool calls that stay silent for ~40 minutes are aborted by the harness; poll in <=150 s windows.
- Editing in this harness: shell heredocs mangle backslashes and some quotes (a Python script in a heredoc silently turned `\n` into real newlines and
  `\\.` into `\\.`). Use the Edit/Write tools, or write a script file and run it.
- CRLF warnings on commit are harmless.

## 7. What live runs have shown (model: free `nvidia/nemotron-3.5-lightning:free` by default)

Run history and what each taught us: (1) first real run hit the old 40-step limit with 1/4 tasks done and cited only its own notes ->
budget, `unfinished`, URL evidence, snapshot context fixes. (2) agent researched without starting tasks, `search_papers` always failed
(papers SQL `$3 IS NULL` ambiguity, fixed in `papers/service.py`) -> task-start guard. (3) comparison task never completed -> synthesis rule;
`update_task` re-stating status was an error -> no-op; `get_research_state` returned nothing -> returns a next-step hint. (4) finished
in 6 min but `satisfied` with 4 unresolved questions, empty evidence, nothing written to the tree, summary rendered as a wall of text ->
finish rules, write requirement, summary CSS. (5) agent looped 26 searches on one task / failed on 3 rejections (selected node not citable,
tree reads counted against the cap) -> cap only searches, citable selected node, lenient URL match. (6) **Latest run (46 steps, ~16 min, 18
searches, ~436k tokens): built the requested tree** (School energy study -> Solar PV / Heat pumps -> Installed cost + Reliability, plus a
Comparison node) and ended `partially_satisfied` with limitations listed. Two items from that run were fixed afterwards but **not re-run
live**: an empty leaf made with `branch_node` (prompt now says leaves holding findings use `write_node`), and final evidence that was the
agent's own Comparison node (now excluded).

## 8. Known issues and next steps (rough priority)

1. **Re-run live and confirm** the last two fixes (no empty leaves, no self-evidence) and a tree with a *structure requested by the user*
   at a different shape (deeper, more branches). Watch the budget: a 5-leaf tree used ~46 of 60 steps.
2. **Research quality is capped by snippets.** `web_search` returns URL + snippet only; there is no page-fetch/read tool. Answers contain
   numbers that are plainly off (e.g. "20-40 kW for a 500-student school") and rules cannot catch that; the check validates *identifiers*,
   not claims. Options: a fetch tool; require each figure in a node to carry a source URL; a verifier pass.
3. **`web_search` is flaky** ("unreadable response", "could not be reached"): 8 of 19 calls failed on one task. No retry beyond one on timeout.
4. **No tool can write into an existing empty node**: `write_node` always creates a child; `ask_node` only works on leaves and sends a
   question. Structure is therefore headings (`branch_node`) and findings (`write_node`); only prompt guidance prevents empty leaves.
5. **The planner often leaves `depends_on` empty** even when the goal says a task depends on others; the synthesis exemption needs it.
   Idea: infer deps from the objective text ("using findings from t1 and t2") or from "compare/summarise" wording.
6. **Plans don't always include tree-building tasks**: structure is built after research unless the model follows the prompt. A runtime-provided
   skeleton step or a planner validation ("goal names a structure -> require write tasks") is untried.
7. **Near-duplicate searches** are bounded only by the per-task cap (6). No dedupe/caching of identical calls.
8. **Weak-model robustness**: bad argument shapes (list as string is coerced; task objective >400 chars is rejected), repeated rejected steps,
   long tails (30-40 s per call late in a run; ~8-9k tokens per step because the full snapshot is resent each step; no compaction by design).
9. **Citation strictness vs usability**: a completion with one unverifiable URL is rejected whole. The error lists valid refs, but the model sometimes
   explores instead of fixing. Consider dropping unverifiable refs with a warning instead of rejecting.
10. **UI gaps**: the status line shows the literal text "Loading..." next to "Working..."; evidence ids are plain text (not links to nodes); no step
    counter; rejected steps are invisible (only in `/trace`); plan-approval UI, manual task reordering and a run history list are not built; the
    window only works with chat collapsed.
11. **Runtime hardening not done**: lease loss isn't detected (a run stalled >300 s could be claimed by a second worker while the first still runs);
    workers die with the API process; events are never purged; no list-runs endpoint (the UI remembers one run id per project in localStorage);
    crash recovery was never exercised live.
12. **Deferred by design** (do not add without asking): thesis-investigation workflow (should plug into the same loop as a prompt/plan source),
    parallel tasks, context compaction, multi-agent, evidence scoring, automatic research-document generation.

## 9. Conventions worth keeping

Smallest change that works; rules live in `ops.check` (pure, unit-tested) and the loop only enforces; the model never sets run status, limits,
execution history or authorises deletes; every new rule gets a rule test in `tests/test_agent_ops.py` and, if it changes the loop, a scripted
scenario in `tests/pg/test_agent_runtime.py` (the fixture `rt` scripts both the LLM and the tools; the fake `write_node` returns a fresh node id).
Frontend follows `docs/DESIGN.md` (library components only, no feature-to-feature imports, look and logic separate).
