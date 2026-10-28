# Debate mode: status, decisions, and what is needed next

## Decisions so far
- LangGraph with `interrupt()`; Lambda workers fed by SQS FIFO (message holds only `debate_id`); sweeper on EventBridge.
- 2 rounds default, max 3. Opening and closing always run. **No concessions**: debaters never leave their side, every round runs unless the user picks a side/stops or the budget is hit.
- Judge is chosen by the server from a different model family than both debaters. First test: Haiku 5.5 debaters (one model on both sides by default; two models are assigned FOR/AGAINST at random), GPT-6 Luna judge, Argon as fallback. Gemini free tier is not used (it may train on prompts).
- Debater models come from a server-side allowlist; the client shows `GET /debates/models` and sends its choice; the server re-validates.
- Only the final output persists (node + `debate_results`). Checkpoints and events are purged; dev flag `retain_artifacts` keeps them.
- `chats` JSONB entries are `{role, content, seq, branch_source, created_at}`. The existing chat endpoint stores the reply as `assistant` and sends stored roles straight to OpenRouter, so debate nodes also use `assistant` (an `llm` role would break follow-up chats). Shared context summarizer lives in utils for debates and normal chats.
- DB is publicly reachable for ACM. Two drivers stay: the backend router uses the existing asyncpg session factory, the Lambdas use psycopg (the LangGraph checkpointer requires it).
- Keys: `OPENROUTER_DEBATE_API_KEY`, `S2_API_KEY` (Semantic Scholar, 1 request/second, shared throttle). Sharees can start debates: like chat, their first write forks the project to them and the debate runs in their copy (via `resolve_target`); owners are unchanged.
- Timing (per node, per segment, active vs wall) and token/cost usage (OpenRouter `usage`) are recorded.
- Tables: `debates`, `debate_events`, `debate_results` (single DDL file, no migration needed).

## State
Built and tested (70 tests, both DB drivers): graph, OpenRouter client, Postgres adapters, API router + SSE, Lambda handlers, DDL.
Not built or untested: real OpenRouter calls, SSL to RDS, SQS/Lambda/EventBridge deployment, semantic search client, shared-project duplicate-on-first-write, frontend.

## Done since the schema files arrived
Node writer, context loader and stand-in schema now match `models.py`, `nodes_router.py` and `flatten.py`. Semantic Scholar client, `.env`-style DATABASE_URL handling, a search failure no longer kills a debate, and a local smoke-test script exist.

## Built since (2026-10-17)
Caching-friendly prompt layout (stable prefix; explicit cache breakpoint for Anthropic/Google models), unattended smoke tester (`--offline --auto-answer --check`), in-process worker for local dev (`debate/pg/local.py`), deploy kit (Dockerfile, SAM template linted with cfn-lint, grants template), `scripts/setup_db.py`, prompt-tuning brief, package guide. 86 tests pass on both drivers.

## Decisions
- Judge: Gemini through OpenRouter (same key, cost tracking, one client; implicit caching works for Gemini 2.5+, explicit breakpoints supported). Caching matters for the debaters (many calls sharing a large context), not for the judge (one call). Direct Gemini API only if a Gemini-only feature is needed. Verify in OpenRouter activity which provider served the request.
- Evidence honesty and the S3 paper pipeline are parked: see `tangent-debate-checkpoint-evidence-and-papers.md`.

## Needed to continue
1. Done: no `has_project_access` needed; results are readable by owner or active sharee, written inline against `projects`/`shares`. Still useful: your real RLS policies on projects/nodes/trees, and your migration tool.
2. `app/core/openrouter.py` (AVAILABLE_MODELS) and `app/context/schemas.py`.
3. Run `scripts/smoke_debate.py` locally with your `.env`, send the output (never the keys), then the prompt-tuning chat (`docs/prompt-tuning-brief.md`).
4. AWS: account/region, SAM CLI + Docker installed, then `deploy/README.md`.
5. RDS: non-owner runtime role (`deploy/runtime_grants.sql`), run `scripts/setup_db.py`, rotate the password after ACM.
6. Decisions: RDS Proxy, history-summary caching, `retain_artifacts` in dev, where secrets live in production.


## Updated 2026-10-18 (RLS)
Live RLS read: `has_project_access(check_project_id uuid)` exists, so debate_results uses it. FORCE RLS is on and the master user is not a superuser or BYPASSRLS, so policies apply to the app. Found a policy cycle between shares_select and projects_sharee_select (see deploy/check_and_fix_shares_rls.sql).

## Updated 2026-10-18
Same-model default with random side assignment, node title/chats for win/pick/stop, `GET /debates/node/{id}`, Haiku/Luna config, SSE real-socket test, sharee forking hook and access-based result policy. 102 tests pass on both drivers.
