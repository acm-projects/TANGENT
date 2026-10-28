# Tangent debate mode: code walkthrough

Written for reading the prototype file by file. Line numbers refer to the files in `debate_proto.zip`. Each section says what the file does, why it is written that way, and where it sits in the architecture.

## 0. The architecture in one paragraph

A debate is a LangGraph graph with one checkpoint saved after every step. The main graph runs: `intake` (load project context) -> `frame` (judge model turns the topic into a proposition and a brief per side, maybe asks you clarifying questions) -> `advance` (a deterministic router) -> two `debater` subgraphs in parallel (FOR and AGAINST) -> back to `advance` -> ... -> `verify` (check citations) -> `judge` -> `finalize` (write the result). `advance` walks the phases: research, opening, rebuttal 1..N, closing. A debater subgraph loops `agent` -> (`search` | `ask_user`) -> `agent` until the agent finishes, then `emit` records the turn. Questions pause the graph through `interrupt()`. In production each stretch of running is one Lambda invocation (a "segment"), and the checkpoint in Postgres is what lets a later invocation continue.

## 1. Reading order

1. `schemas.py` (the data shapes)
2. `state.py` (what the graph remembers)
3. `deps.py` (what the graph needs from the outside world)
4. `graph.py` (the logic, read top to bottom)
5. `judge_view.py`, `runner.py`, `context.py`
6. `fakes.py`, then `tests/`

---

## 2. `debate/schemas.py` (121 lines): the vocabulary

Plain Pydantic models. Nothing here runs a debate; it defines what the pieces are.

- `Side`, `Phase`, `EndReason` (lines 8-18): string literals. `EndReason` mirrors the `debate_end_reason` enum in the DDL, so the code and the database agree on the same seven values.
- `question_id(prompt)` (line 21): lowercases, collapses whitespace, SHA-1, first 8 hex characters. **Why:** if FOR and AGAINST both ask "What's your budget?" at the same time, they get the same id, so you see one question and one answer satisfies both. The normalization means "What's your budget?" and "what's  your budget?" count as the same question.
- `Claim` (25): one argument point with an id and the evidence ids backing it. **Why claims exist:** the opponent can only attack or acknowledge something specific, and the judge scores specific claims, so each point needs a stable id.
- `TurnOutput` (37): what a debater produces in one turn: `thinking` (a list of short notes shown on screen), `argument`, `claims`.
- `Turn` (45): a `TurnOutput` plus bookkeeping: side, phase, round, `truncated` (the turn was cut short by a control signal or step cap).
- `Question` (53): one question card for the UI. `model_post_init` fills in the id from the prompt if none was given. `options` plus `allow_other` is the multiple-choice-with-escape-hatch shape.
- `QA` (65): a question with its answer and who asked. This is what gets stored as "user context" and later fed to the agents and judge.
- `Evidence` (72): one paper from semantic search.
- `OpponentView` (80): **deliberately only argument, claims and stance.** No thinking. This is the type the debater receives about its opponent, so the "opponent never sees your thinking" rule is enforced by the type itself.
- `SearchAction`, `AskAction`, `FinishAction` (86-100) and `AgentAction` (103): the three things an agent can do each step. This is how "tools" are modelled: instead of letting the model call arbitrary functions, every step returns exactly one of these. The real OpenRouter adapter will translate tool calls into these.
- `FrameResult` (106): the proposition, a brief for each side, and optional clarifying questions.
- `JudgeVerdict` (112): winner is `"A"`, `"B"` or `"none"` (never "for"/"against", because the judge must not know sides). `would_have_chosen` is used when you pick the winner yourself. Also confidence, rationale, summary, final output, scores, counterpoints, and "verdict flips if".

**Connects to:** the schemas are the contract between the graph and the model adapter. Structured outputs from OpenRouter should validate straight into these.

---

## 3. `debate/state.py` (83 lines): what the graph remembers

LangGraph keeps state as a dict that gets checkpointed after every step. Two states exist.

**Reducers (lines 7-25).** When two parallel branches (FOR and AGAINST) both write the same key, LangGraph needs a rule for combining them.
- `merge_dict`: later keys win (used for the evidence pool).
- `sum_dict`: adds numbers per key (used for `asks_used`, so each side's count adds up).
- `merge_by_id`: appends items whose `id` is not already present (used for `user_context`; this is what de-duplicates a question answered once for two askers).
- `operator.add` on lists (used for `turns` and `metrics`): just concatenates.

**`DebateState` (28-50):** the main graph.
- Inputs: `debate_id`, `topic`, `rounds`.
- Loaded once: `context_text`, then `proposition`, `side_briefs`.
- Accumulated across the debate (with reducers): `user_context`, `evidence_pool`, `turns`, `asks_used`, `metrics`.
- Control flow: `phase`, `round`, `dispatch` (the instructions `advance` hands to the debaters), `end_reason`, `picked_side`, `applied_control_id`.
- Late results: `citation_report`, `ab_map`, `verdict`, `result_node_id`.

**`DebaterState` (53-83):** the subgraph's private state.
- Keys that start with `in_` are inputs passed down from the main graph.
- The other keys are the subgraph's scratch space (`steps`, `searches`, `pending_search`, `pending_ask`, `action_kind`, `finish`, `forced`).
- The last five keys (`turns`, `evidence_pool`, `user_context`, `asks_used`, `metrics`) are outputs that flow back up to the main graph, with the same reducers.

**Why the `in_` prefix:** I hit this class of LangGraph problem: if an input key and an output key share a name, a subgraph can cause conflicting writes or double-counting through the reducer. Inputs and outputs use different names, so every output key is written only by the debater and read only by the main graph.

**Why plain dicts, not Pydantic objects, in state:** checkpoints are serialized to Postgres. Plain dicts serialize reliably; custom classes are a known source of serialization trouble with LangGraph checkpointers.

---

## 4. `debate/deps.py` (76 lines): the seam to the real world

Everything the graph needs from outside is an interface (a `Protocol`), bundled into one `Deps` object.

- `AgentContext` (11): everything an agent is shown for one step: side, phase, round, proposition, its brief, the project context, user answers so far, evidence, the opponent's last turn, its own steps so far, and three permissions: `may_search`, `may_ask`, `force_finish`.
- `JudgeView` (29): the anonymized transcript text, the labels, and the evidence actually cited.
- `Brain` (35): three methods, `frame`, `step`, `judge`. **This is where OpenRouter plugs in.** Models are chosen by the user for FOR and AGAINST; the judge is server-chosen. The real `Brain` picks the model by `ctx.side`.
- `Search` (41): the semantic search client.
- `Control` and `ControlStore` (45-53): the pick-side/stop signal. `pending(debate_id, applied_id)` returns a control request that has not been applied yet. Production reads `debates.control`.
- `Emitter` (56): writes events; returns False when the key was already used (idempotency). Production inserts into `debate_events` with `ON CONFLICT DO NOTHING`.
- `ResultWriter` (60): creates the node and `debate_results` row; must be idempotent.
- `Deps` (65): the bundle, plus limits: `ask_cap=2` asks per side, `search_cap=3` searches per turn, `turn_step_cap=6` steps per turn, `max_agent_steps` (a crude budget, see gaps).

**Why:** the graph logic never imports OpenRouter, psycopg or SQS. That is why it could be tested with scripted fakes, and why swapping a real adapter in does not change the graph. The method bodies here are `...` because they are signatures only. They are not unfinished logic.

**Where it lives at runtime:** the `Deps` object is passed in `config["configurable"]["deps"]` (see `_deps` in graph.py). It is not stored in state, so it is never checkpointed.

---

## 5. `debate/graph.py` (460 lines): the core

### Helpers (lines 27-58)
- `_deps`, `_did`: pull deps and the debate id (`thread_id`) from the run config.
- `_other(side)`: the opposing side.
- `_metric(...)` (39): builds a timing record: node name, side, phase, round, and `duration_ms` measured from a start time.
- `_qa_from_reply(...)` (50): turns an interrupt reply into `QA` records. Returns nothing if the reply is a skip (see the control section) or has no answers.

### The debater subgraph

**`agent_node` (61-128): one decision step.**
1. Check for a pending control signal (line 68). If one exists, or the turn has used `turn_step_cap` steps, `forced` becomes true: the agent must finish now.
2. Merge what the agent knows: inputs from the main graph (`in_user_context`, `in_evidence`) plus anything gained during this turn (`user_context`, `evidence_pool`). Work out how many asks are left (`in_asks_remaining` minus what this side already used).
3. Build the `AgentContext` with the permissions: may search only if the phase allows it and the per-turn search cap is not hit; may ask only if the phase allows and asks remain.
4. Call `brain.step`.
5. **Enforcement (94-104):** if forced and the agent didn't finish, replace its action with a finish ("turn cut short"). If the agent asks for a search or ask it isn't allowed, record a `rejected` step and loop back to `agent` (`action_kind: "again"`). The model is never trusted to follow the permissions; the graph checks.
6. For a search: emit `thinking` and `tool_called` events and set `pending_search`. For an ask: emit `thinking` and store at most 3 questions in `pending_ask`. For a finish: store the turn in `finish`.
7. Event keys (like `think:{did}:{side}:{phase}:{rnd}:{step}`) make re-emitting harmless if Lambda retries this step.

**`search_node` (131-146):** runs the search, adds results to `evidence_pool`, adds an observation to `steps` (so the next `agent` call sees it), bumps `searches`, clears `pending_search`, records a timing metric.

**`ask_user_node` (149-168): the pause.**
- Calls `interrupt({...})` with the side, phase, round and the questions. The first time this node runs, `interrupt` stops the whole graph and LangGraph saves a checkpoint.
- On resume, the same call returns your reply instead. The node converts it into `QA` records, writes `user_context`, adds 1 to this side's `asks_used`, and clears `pending_ask`.
- If the reply was a skip (you pressed pick/stop while it waited), no answers are stored (`skipped`).
- **Why a separate node:** on resume LangGraph re-runs only the node that was interrupted. Because `ask_user` does nothing else, a resume cannot repeat a search or a model call.

**`emit_node`: finishes a turn.**
- Builds the `Turn` and emits `turn_completed` (includes the thinking list and argument, which is what the frontend shows). There is no concession mechanism: a debater never leaves its side, so every round always runs.
- Returns `{"turns": [turn]}`.

**`route_agent` (215) and `build_debater` (219):** the subgraph wiring. After `agent`, the `action_kind` decides where to go: `search`, `ask_user`, `emit`, or `again` (back to `agent`). `search` and `ask_user` both return to `agent`. `emit` goes to END.

### The main graph

**`intake` (233-241):** calls `context_loader` (production: your lineage builder, given the debate id) and stores the text in state. Emits a `phase_changed` event with the node count. The context is loaded once and frozen in state, so a debate does not change if someone edits the project mid-run.

**`frame` (244-253):** calls `brain.frame`, stores the proposition, side briefs and any clarifying questions, records a timing metric.

**`route_after_frame` / `ask_frame` (256-266):** if the frame produced questions, `ask_frame` pauses with `interrupt` (scope "frame") and stores the answers as user context. Otherwise it goes straight to `advance`.

**`decide` (269-285): the phase state machine, pure and easy to test.**
- Closing done, or user stopped, or budget exhausted -> `done`.
- User picked a side -> go to closing with only that side.
- Start -> research -> opening -> rebuttal round 1.
- If rounds remain -> next rebuttal round; otherwise closing with `rounds_exhausted`.

**`advance` (288-359): the gate that runs between every phase.**
1. Checks for a control request (292-304). A new one sets `user_picked` or `user_stopped` and emits `control_applied`. Without one, it checks the budget.
2. Calls `decide` for the next phase.
3. Builds a `dispatch` entry per side: what the opponent last said (`OpponentView`, no thinking), remaining asks, and the permissions for that phase: search in research and rebuttal, ask in research/opening/rebuttal.
4. Emits `phase_changed` and returns the updates.

**`route_advance` (362-379):** if `done`, go to `verify`. Otherwise return a list of `Send` objects, one per side. This is LangGraph's fan-out: both debaters run at the same time, each with its own copy of the inputs.

**`verify` (382-392):** deterministic. For every non-research turn it checks each cited evidence id exists in the evidence pool. Anything missing goes into `citation_report`, which the judge is told about. This is what stops a model from inventing a paper id.

**`judge` (395-408):** randomizes which side is "A" with `rng`, builds the anonymized view, and calls `brain.judge`. If you picked a side, it passes `fixed` (the label of your choice) so the judge writes for that side. Then it maps the A/B answer back to for/against; if you picked, the winner is forced to your pick and the judge's own preference is kept as `would_have_chosen_side`.

**`finalize` (411-438):** gathers everything permanent into one payload (proposition, winner, confidence, summary, final output, rationale, scores, counterpoints, flip conditions, cited papers, clarifications, end reason, timings) and calls `writer.create_result`. Emits `completed` with the node id. Purging events and checkpoints is the runner's job after this (not in this file).

**`build_graph` (441-460):** wires it all together. The compiled debater subgraph is added as one node of the main graph, and `debater -> advance` closes the loop. The checkpointer is passed in. This is where Postgres goes in production.

---

## 6. `debate/judge_view.py` (61 lines): fairness

Builds what the judge reads.
- Drops research turns (private scratch work).
- Renames every claim id to `A1, A2, B1...` (lines 13-20) so ids like `for-opening-0-1` never reveal a side.
- Writes: proposition, project context, your clarifications, then the transcript labelled `Position A/B`, with each claim and its evidence ids.
- Withdrawals are described neutrally ("Position A withdrew B2").
- Adds notes for truncated turns and unverified citations.
- Never includes thinking or model names.

**Why:** a judge that knows "this is the FOR side" or "this came from model X" can be biased. Randomizing A/B each debate and stripping side words keeps the verdict about the arguments.

---

## 7. `debate/runner.py` (68 lines): the Lambda-facing part

- `Segment` (10): the result of one stretch: `status` is `done`, `paused` (with the interrupts), or `continue` (ran out of time).
- `pending_interrupts` (15): reads the saved state to find open interrupts.
- `run_segment` (25): streams the graph. After every superstep it checks `time_left_ms()`; if less than `min_slice_ms` remains it stops and returns `continue`. When the stream ends, it inspects the saved state: interrupts -> `paused`, remaining nodes -> `continue`, otherwise `done`. **This is the whole Lambda time-slicing mechanism.** A Lambda handler calls this with `time_left_ms = context.get_remaining_time_in_millis`.
- `merge_pending` (50): merges the open interrupts into one list of questions for the UI, combining identical question ids and noting who asked.
- `build_resume` (60): builds the `Command(resume=...)` mapping each interrupt id to its answers (or `{"skip": True}`).

**Not here yet:** setting `debates.status`, writing `pending_questions`, enqueueing the next segment, heartbeating `lease_until`, and purging after `done`. Those are the Lambda handler.

---

## 8. `debate/context.py`: project history as context

It mirrors your `app/context/flatten.py`, so a debate sees exactly what a normal chat message would.
- `NodeRow(id, chats)` and `NodeStore.path(node_id)`: the path from the root to the starting node (the same recursive SQL as `nodes_router._PATH_SQL`).
- `serialize_node`: copy of your `_serialize_node`. Messages tagged `branch_source` (the two snapshots on a merge node) collapse into ONE user turn at the position of the first tagged message. Roles `assistant` and the older `llm` both read as `assistant`.
- Merge sources are **not** walked: a merge node already carries both branches inside its own chats, so walking `node_merge_sources` would duplicate them.
- `build_lineage_context`: renders each node as a block. If everything fits the token budget it joins them. Otherwise it keeps the newest nodes that fit, trims the newest from the front if even that is too big, and summarizes the dropped older nodes with the `summarize` callback. Your normal chat does not do this (it sends everything). Debates multiply the context by three agents, so they get a budget.

---

## 9. `debate/fakes.py` (174 lines): test scaffolding only

- `InMemoryControl`: you call `request(...)` to simulate pressing pick/stop.
- `InMemoryEmitter`: records events and refuses duplicate keys (the same idempotency the DB will give).
- `InMemoryWriter`: stores the result once per debate id.
- `FakeSearch`: returns one fake paper per query.
- `ScriptedBrain`: a fake model. Tests give it a script keyed by (side, phase, round, step) to force exact behaviour (ask here, finish early there). Without a script, it searches once in research and then finishes with a generic turn. It records every context and judge view it received so tests can inspect them (this is how the "no thinking leaks" and "no side words reach the judge" tests work).
- `make_deps(...)`: assembles a `Deps` of fakes.

---

## 10. `tests/` (35 unit tests, 35 Postgres tests)

- `helpers.py`: `drive(...)` runs a whole debate by calling `run_segment` in a loop and answering pauses, like the Lambda + API would. `make_config` sets `thread_id` and deps.
- `test_flows.py` (16 tests): behaviour end to end: happy path and blindness, judge anonymity, rebuttal questions and dedupe, ask not allowed in closing, ask cap per side, frame questions, all rounds always run, pick side, stop, control while waiting, budget, unverified citations, resume on a fresh graph, time-slicing equivalence, emitter dedupe.
- `test_context.py` (6 tests): ordering, summarizing under budget, trimming a huge node, merge sources, cycles.

---

## 11. One debate, traced

1. API creates the `debates` row, enqueues SQS. Lambda segment 1 starts: `intake` -> `frame`.
2. `advance`: no phase yet -> `research`; two `Send`s.
3. Each debater: `agent` -> `search` -> `agent` -> `emit` (thinking events stream to the UI).
4. `advance` -> `opening` (blind: no opponent view). Then `rebuttal 1`: each side sees the other's opening.
5. In rebuttal, FOR's agent asks "what's your budget?" -> `ask_user` calls `interrupt`. AGAINST finishes normally. The graph is saved and the segment returns `paused`. Status becomes `awaiting_input`. No Lambda is running.
6. You answer; the API enqueues a resume. A new Lambda loads the checkpoint, `ask_user` returns your answer, FOR's `agent` continues with the answer in context and finishes.
7. `advance` -> rebuttal 2 -> closing -> `done`.
8. `verify` -> `judge` -> `finalize` writes the node. Then purge.

---

## 12. Update: what changed after this walkthrough was written

New files: `metrics.py` (usage and timing summaries), `prompts.py` (system and user prompts), `openrouter.py`, and `pg/` (`db.py`, `adapters.py`, `store.py`, `checkpointer.py`, `worker.py`).

Changes to the files above:
- `Emitter.emit` and `ControlStore.pending` are now `async`, because the real ones hit the database.
- `Usage` (schemas.py) is attached to every model result. `graph.py` collects it in `usage` and every working node now writes a timing metric with `started_at_ms`. The budget counts agent steps and, optionally, cost (`max_cost_usd`).
- `judge` now turns A/B back into FOR/AGAINST in the stored scores and text (before, the saved verdict said "Position A").
- `runner.run_segment` always completes at least one superstep per call and checkpoints with `durability="sync"`. Without the first change a Lambda started with little time left could loop forever without progress.

The previous list of gaps is now: no sweeper for stale leases, no SQS or Lambda handler, no endpoints, no search client, and the node SQL now matches your real `models.py`.

## 13. Update: API, queue, Lambda

- `pg/api.py`: `build_router(...)`. Endpoints: `GET /debates/models`, `POST /debates` (checks the model allowlist on the server, picks a judge from a different family, enforces the per-user active limit, creates the row, enqueues), `GET /debates/{id}`, `POST .../answer`, `POST .../control`, `POST .../cancel`, `GET .../events` (SSE). The stream sends a `state` snapshot first, then events with their database id (so `Last-Event-ID` replay works), a heartbeat comment, and a final `done` event. It waits one extra poll after the status flips, because the last event is written just after.
- `pg/queue.py`: `SqsEnqueuer`. The message holds only the debate id. Answers and control signals are stored in `debates.resume_payload` and `debates.control`.
- `pg/handler.py`: `handle` (SQS batch, partial failures), `handler` (Lambda entry), `sweep` and `sweeper` (re-queue stuck debates, expire overdue ones, delete old events, clean checkpoints).
- Event purge moved: checkpoints are deleted when the debate ends, events a few minutes later by the sweeper, so a client that reconnects can still replay.
