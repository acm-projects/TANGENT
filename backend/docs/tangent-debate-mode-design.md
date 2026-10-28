# Tangent — Debate Mode design (as of 2026-10-06)

Status: the orchestration, the OpenRouter adapter, the Postgres adapters, the SQS queue and Lambda handlers, the router and the SSE stream are built and tested (unit tests plus integration tests on a real Postgres 16 with the LangGraph Postgres checkpointer, on both the psycopg and asyncpg drivers). Not built or deployed: the AWS resources themselves, the search client, duplicate-on-first-write for shared projects, the frontend. DDL lives in `tangent-debate-mode-ddl.sql`; integration steps are in `tangent-debate-integration-and-deploy.md`.

## What it does
The user starts a debate from any node. Two debaters (FOR and AGAINST, models picked by the user through OpenRouter) argue a proposition. A judge model chosen by the server decides. The winning output becomes a new node in the project and the user keeps chatting from it. Only the final node and a small `debate_results` row persist; transcripts, events and checkpoints are transient.

## Graph
request (API) -> intake -> frame -> [ask_frame] -> advance -> debater x2 -> advance -> ... -> verify_citations -> judge -> finalize -> runner purge.

- `intake`: loads the lineage context once and freezes it in graph state.
- `frame`: judge-model call. Produces the proposition, a brief per side, and optional clarifying MCQs (`ask_frame` interrupts).
- `advance`: deterministic gate and phase router. Order: research, opening, rebuttal rounds 1..N, closing. It applies user control and budget limits, and builds the Send payloads for the next phase.
- `debater`: one compiled subgraph used for every phase: `agent` loops with `search` or `ask_user`, then `emit`. Fan-out is two parallel Sends.
- `verify_citations`: deterministic. Every cited evidence id must exist in the evidence pool.
- `judge`: sees an anonymized transcript (Position A or B, randomized, claim ids renamed, no thinking, no model names). Structured output.
- `finalize`: creates the node and `debate_results` in one idempotent transaction (keyed by `debates.result_node_id`).

`rounds` counts rebuttal exchanges (1 to 3, default 2). Opening and closing are always included.

## Context from the project
The debate starts from a node (`parent_node_id`). Context is the lineage up to that moment: walk `parent_id` to the root (same recursive query and the same `branch_source` collapsing as `flatten.py`, so debate context equals chat context; merge sources are not walked because merge nodes carry their branches inside their own chats). `debate/context.py` adds a token budget: newest nodes kept in full, oldest summarized by a cheap model. Both debaters and the judge get the same context. Like prompting and branching today, only the project owner can start a debate; a sharee gets a 403 and is told to fork the project first.

## Debater turn
- Structured output: `thinking` (short working notes), `argument`, `claims` (id, text, evidence ids).
- Tools: `search_papers` (semantic search API, capped per turn) and `ask_user` (routed to its own node, not the tool node, so resume never replays searches). Results and user text are untrusted input.
- `ask_user` is allowed in research, opening and rebuttal, never in closing. Cap: 2 asks per side per debate, up to 3 questions per ask. Parallel asks are merged by a hash of the normalized question text; one answer resumes every matching interrupt in a single call.
- No concessions. A debater never leaves its side and acknowledges a fair opponent point inside its argument. Every round runs in full unless the user picks a side or stops, or the budget is hit. The judge decides and may return `no_clear_winner`.
- Opponents see only `argument`, `claims` and `stance`. Thinking is for the user's screen and is never shown to the opponent or judge.

## User control (interrupt)
`POST /debates/{id}/control` writes `debates.control` ({id, action, side}). Actions: `pick_side` (the user decides) and `stop` (the judge decides now).
- Cooperative: each agent checks before every LLM call and `advance` checks at every phase boundary. An in-flight LLM call finishes, so latency is about one call.
- While waiting on a question, the API resumes the interrupts with `skip` and sets control.
- `pick_side`: the chosen side writes a closing, the judge runs in fixed-winner mode and also reports who it would have chosen. `end_reason = user_picked`.
- `stop`: no closings, the judge decides. `end_reason = user_stopped`.

## Showing thinking
Each agent step emits a `thinking` event, and each finished turn emits `turn_completed` with the full thinking list. This is model-agnostic. Event keys make replays idempotent (`debate_events (debate_id, event_key)` unique). Live text is added on top: `token` events batched about every 250 ms (see FRONTEND_CONTRACT.md).

## Execution
- Worker: Lambda (container image) triggered by an SQS FIFO queue, `MessageGroupId = debate_id`. One task, `run_segment(debate_id, resume)`. A segment ends at END, at an interrupt, or when the time slice runs out (checked at superstep boundaries with `stream_mode="values"`; continue with input `None`).
- Interrupts end the segment, so waiting for the user holds no worker.
- Safety: `debates.lease_until` heartbeat, `queued` status, visibility timeout at least 6x the function timeout, dead-letter queue. Cancel and control are DB flags, never `revoke`.
- Current DB: RDS is publicly reachable (set up for ACM), so Lambda can run outside the VPC with no NAT. The DB password is the master key to all user data, since identity is a per-transaction setting. Use a non-owner runtime role, check `rolbypassrls`, enforce SSL, rotate after ACM.
- API: localhost during development, EC2 later. Server to client over SSE with `Last-Event-ID` replay, client to server over plain POST (`/debates`, `/answer`, `/control`, `/cancel`). Fetch-based SSE client, because the API reads a Bearer header.

## Tracking
- Timing: every working node records `started_at_ms` and `duration_ms` (intake, frame, advance, agent, search, emit, verify, judge; waiting on the user is not timed). `timing_summary` gives seconds per phase and round. Each Lambda segment is recorded in `debates.segments`; `active_ms` is their sum, `wall_ms` is created to completed, `waited_ms` is the difference.
- Usage: the Brain attaches a `usage` record to every model call (tokens, reasoning tokens, cached tokens, OpenRouter `cost`, latency, generation id). `usage_summary` totals it by role and model. `max_cost_usd` stops the debate with `budget_exhausted`.
- Both are copied into `debate_results`, so they outlive the transient tables.

## Adapters
- OpenRouter: agent steps use tool calling (`search_papers`, `ask_user`, `submit_turn`, offered only when allowed); frame and judge use strict `json_schema`. Requests set `provider.require_parameters` and `data_collection: deny` (project chats are private). Claim ids are assigned by the code, not the model. One repair retry on invalid output; transient HTTP errors retried; 401/402 fail the debate with a code.
- Postgres: SQLAlchemy async with raw SQL. Identity is set per transaction (`app.current_user_id`); the worker reads and leases the debate under the maintenance flag, then acts as the owner. Checkpoints use `AsyncPostgresSaver` in the `langgraph` schema with `durability="sync"`.

## Verified in the prototype (langgraph 1.2.13)
Parallel interrupts from two Send branches resume together by interrupt id. Resume works on a fresh graph instance. Time slicing at superstep boundaries gives the same result as an uninterrupted run. Mutation checks confirmed the tests catch: asking in closing, ask cap, hash dedupe, thinking leak, side leak to the judge, ignored control.

## Open items
- Does `chats` JSONB have a role/content shape? `context.py` assumes a list of {role, content}.
- Which model families are allowed as judge, and who owns the allowlist.
- Whether the final node should keep a compact argument map (currently only citations, counterpoints and flip conditions persist).
