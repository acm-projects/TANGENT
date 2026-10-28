# Package guide: what each file is, where it goes, how to run it

## Where things go in your repo

```
your-backend/
├─ app/                          (your existing code)
│  ├─ models.py                  EDIT: add "debate" to node_type_enum
│  ├─ context/schemas.py         EDIT only if node_type is a Literal there: add "debate"
│  └─ routers/
│     └─ debates_router.py       NEW: copy from integration/debates_router.py, fill in the model lists
├─ debate/                       NEW: copy the whole folder (it is a plain Python package)
├─ scripts/                      NEW: smoke_debate.py, setup_db.py
├─ deploy/                       NEW: Dockerfile, template.yaml, runtime_grants.sql, README.md
├─ tests/ (debate tests)         NEW: copy next to your tests (tests/pg needs a throwaway Postgres)
├─ requirements-lambda.txt       NEW: the Lambda image's dependencies
└─ docs/                         NEW: design, walkthrough, DDL, prompt-tuning brief
```
`main.py`: add `from app.routers import debates_router` and `app.include_router(debates_router.router)`.
Add `langgraph`, `langgraph-checkpoint-postgres`, `psycopg[binary]`, `httpx`, `boto3` to the backend's requirements
(`requirements.txt` lists them). `debate/` imports itself with relative imports, so the folder can be renamed or nested.

## Run order

1. `pip install -r requirements.txt`
2. Offline check, no keys: `python scripts/smoke_debate.py --offline --topic t --auto-answer --check` and `python -m pytest`
3. Real models, on your machine, keys from `.env` (`OPENROUTER_DEBATE_API_KEY`, `S2_API_KEY`):
   `python scripts/smoke_debate.py --topic "..." --for-model <id> --against-model <id> --judge-model <id> --rounds 2 --auto-answer --check --dump out.json`
4. Database (once): `python scripts/setup_db.py --ddl --saver`, then review `deploy/runtime_grants.sql`.
5. Backend with debates, no AWS: leave `DEBATE_QUEUE_URL` unset; the router runs the worker in-process (`debate/pg/local.py`).
6. AWS: follow `deploy/README.md` (`sam build`, `sam deploy --guided`), then set `DEBATE_QUEUE_URL` in the backend.

## Core files (no database, no AWS)

| File | What it does | Why it exists |
|---|---|---|
| `debate/schemas.py` | Data shapes: claims, turns, questions, evidence, verdict, token usage | The contract between models and the graph |
| `debate/state.py` | LangGraph state for the debate and for one debater's turn | Parallel debaters merge safely through reducers |
| `debate/deps.py` | Interfaces the graph calls (model, search, events, control, writer) and limits | Lets tests use fakes and production use Postgres/OpenRouter |
| `debate/graph.py` | The architecture: intake, frame, advance, debater subgraph (agent/search/ask_user/emit), verify, judge, finalize | Orchestration, pause/resume, per-node timing |
| `debate/prompts.py` | All prompt text | The one file prompt tuning changes |
| `debate/judge_view.py` | Builds the anonymous transcript the judge sees | Blind judging: no model names, thinking, or side words |
| `debate/openrouter.py` | OpenRouter client + `OpenRouterBrain` (tool calls, strict JSON, retries, usage/cost, cache breakpoints) | The real models |
| `debate/search_s2.py` | Semantic Scholar search with a shared 1 req/s throttle and 429 retry | The debaters' `search_papers` tool |
| `debate/context.py` | Parent-chain history, same rules as your `flatten.py`, with a token budget | A debate starts from any node and sees the same history a chat would |
| `debate/runner.py` | Runs the graph in time slices; detects pauses for user input | Lets one debate span many Lambda invocations |
| `debate/metrics.py` | Timing summaries by phase and round; usage summaries by role and model | Your "how long / how many tokens" requirement |
| `debate/fakes.py` | In-memory fakes and a scripted model | All unit tests and the offline smoke run |

## `debate/pg/` (Postgres and AWS)

| File | What it does |
|---|---|
| `db.py` | Engines (psycopg or asyncpg), your jdbc-style `DATABASE_URL`, SSL for remote hosts, per-transaction RLS identity |
| `checkpointer.py` | LangGraph's Postgres checkpoint store (`langgraph` schema), setup and purge |
| `store.py` | Every state change: create, answer, control, cancel, leases, heartbeats, segments, failures, sweeper queries |
| `adapters.py` | Events table writer, control reader, result node writer (title, summary, fork_index, chats), node path reader |
| `worker.py` | One Lambda run of a debate: lease, load, run a slice, pause/finish/fail/re-queue |
| `queue.py` | SQS FIFO sender (message = debate id only) |
| `handler.py` | Lambda entry points `handler` (SQS worker) and `sweeper` (EventBridge) |
| `api.py` | The `/debates` router: models, start, get, answer, control, cancel, SSE events with replay |
| `local.py` | In-process worker for local development, no AWS |

## Other folders

- `scripts/smoke_debate.py`: one debate in-process; `--auto-answer`, `--check`, `--offline`, `--dump`, `--events-out`.
- `scripts/setup_db.py`: applies the DDL and creates the checkpoint tables.
- `integration/`: the router shim for your backend and the list of backend edits.
- `deploy/`: Dockerfile, SAM template (SQS FIFO + DLQ, two Lambdas, schedule), DB grants template, deploy steps.
- `tests/`: 55 unit tests; `tests/pg/` 47 integration tests that need a throwaway Postgres (`TEST_PG_ADMIN_URL`).
  `tests/pg/base_schema.sql` is a stand-in for your tables and is never part of your migrations.
- `docs/`: `tangent-debate-mode-design.md` (architecture), `tangent-debate-code-walkthrough.md` (line-level tour),
  `tangent-debate-mode-ddl.sql` (tables), `prompt-tuning-brief.md` (paste into the tuning chat),
  `tangent-debate-status-and-next-steps.md`.

## What is tested and what is not

Tested on a real Postgres 16, on both drivers: row-level security, pause/resume, time slicing, leases, cancel, the full
API -> queue -> worker -> SSE -> answer -> replay flow, the in-process worker. Template linted with cfn-lint.
NOT tested: calls to the real OpenRouter and Semantic Scholar (mocks only), SSL to RDS, a real SQS/Lambda/EventBridge
deployment, your real RLS policies, prompt quality with real models.
