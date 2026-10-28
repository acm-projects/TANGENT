# Debate mode: putting it in the project, and deploying it

Everything here was tested against a local Postgres 16, except the AWS parts, which were not deployed.

## 1. Copying the code into the backend
1. Copy `debate/` into the backend repo as a package, for example `app/debate/`. All imports inside it are relative, so the folder name does not matter.
   `debate/context.py` has no framework imports. It can live in `utils/` instead and be used by normal chats too (see section 4).
2. Copy `tests/` next to your other tests. Do not copy `tests/pg/base_schema.sql` into your migrations. It is a stand-in so the tests can run on an empty database.
3. `pip install -r requirements.txt`.
4. Run the DDL (`tangent-debate-mode-ddl.sql`) once on your database.
   Then run `setup_saver(DATABASE_URL)` once (from `debate/pg/checkpointer.py`). It creates LangGraph's tables in the `langgraph` schema.
5. The node SQL in `debate/pg/adapters.py` matches your `models.py` (`nodes`: tree_id, project_id, parent_id, fork_index NOT NULL and unique per parent, node_type, status, title, summary, chats, created_by_id). The writer takes the next free `fork_index` (max + 1, like `fork_node`), retries on a collision, writes `title`/`summary`, and stores chats as `{role, content, seq, branch_source, created_at}` with role `assistant` for the reply. In `app/models.py` add `"debate"` to `node_type_enum`, otherwise the ORM raises on debate nodes. See `integration/README.md`.
6. Mount the router in the FastAPI app:

       from app.debate.pg.api import build_router, DebateSettings, ModelOption, JudgeOption
       from app.debate.pg.db import make_engine, make_factory
       from app.debate.pg.queue import SqsEnqueuer
       factory = make_factory(make_engine(DATABASE_URL, driver="asyncpg"))   # or "psycopg"
       app.include_router(build_router(
           factory=factory,
           current_user=get_current_user_id,        # your dependency; it must return the user id as a string
           enqueue=SqsEnqueuer(os.environ["DEBATE_QUEUE_URL"]),
           settings=DebateSettings(allowed_models=[...], judges=[...]),
       ))

   The router opens its own transactions and sets `app.current_user_id` itself, so it does not use `get_db_session`.
   That is deliberate: the streaming endpoint must not hold one request-long transaction open.

## 2. Database drivers
Your FastAPI backend can keep asyncpg. The debate code runs on either driver: pick it with `make_engine(url, driver=...)` or the
`DEBATE_DB_DRIVER` environment variable (default `psycopg`, which the Lambda should use so its image needs one driver). The tests pass on both.
The only place that always needs psycopg is LangGraph's Postgres checkpointer, so psycopg is installed either way.

## 3. AWS setup (not deployed or tested)
- **Queue:** SQS FIFO. Visibility timeout at least 6 times the function timeout. Add a dead-letter queue (maxReceiveCount about 5). Use SQS-managed encryption.
- **Worker Lambda:** container image, handler `debate.pg.handler.handler`, timeout 900 s, memory 1024 MB. Event source mapping with batch size 1 and `ReportBatchItemFailures` on.
  Set `DEBATE_MIN_SLICE_MS` above the longest single model call (default 150000), because a segment only stops between graph steps.
- **Sweeper Lambda:** same image, handler `debate.pg.handler.sweeper`, run by EventBridge Scheduler every 2 minutes. It re-queues stuck debates, fails overdue ones, deletes old events and cleans checkpoints of cancelled debates.
- **Environment variables:** `DATABASE_URL` (the jdbc-style value is accepted; `DB_USER`/`DB_PASSWORD` fill in credentials; remote hosts get `sslmode=require`), `OPENROUTER_DEBATE_API_KEY`, `S2_API_KEY`, `DEBATE_QUEUE_URL`, optional `DEBATE_SEARCH_FACTORY` (defaults to the Semantic Scholar client `debate.search_s2:from_env`), optional `APP_URL`, `DEBATE_SUMMARY_MODEL`, `DEBATE_CONTEXT_TOKENS`, `DEBATE_MAX_COST_USD`, `DEBATE_MIN_SLICE_MS`.
- **API side:** needs `sqs:SendMessage` on the queue. The worker needs `sqs:ReceiveMessage/DeleteMessage/GetQueueAttributes`. The sweeper also needs `sqs:SendMessage`.
- **Database access:** use a non-owner role for the runtime, enforce SSL, and rotate the password when the ACM work ends (see the earlier security notes).

## 4. Shared context helper
`build_lineage_context` in `debate/context.py` walks parent and merge-source nodes, keeps the newest nodes in full, and summarizes the oldest through a callback.
Chats could call the same function. One improvement worth making for chats: store each node's summary once instead of re-summarizing on every message.
