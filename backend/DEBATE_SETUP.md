# Debate mode: drop-in

Unzip this over your backend project root (the folder that contains `app/`). It only adds files; it overwrites nothing of yours
unless you already have a `debate/` folder, `scripts/setup_db.py` or `scripts/smoke_debate.py`.

Added: `debate/` (the package), `app/routers/debates_router.py`, `scripts/setup_db.py`, `scripts/smoke_debate.py`,
`docs/tangent-debate-mode-ddl.sql`, `docs/FRONTEND_CONTRACT.md`, `requirements-debate.txt`.

## Commands (run from the project root)
    pip install -r requirements-debate.txt
    python scripts/setup_db.py --ddl --saver        # ONCE: tables, enums, RLS, 'debate' node type, LangGraph tables

## Four edits in your own files
1. app/models.py:  node_type_enum = PGEnum("standard", "temporary", "debate", name="node_type", create_type=False)
2. app/context/schemas.py: if NodeOut/NodeMeta declare node_type as a Literal, add "debate".
3. app/main.py:
       from app.routers import debates_router
       app.include_router(debates_router.router)
4. .env: OPENROUTER_DEBATE_API_KEY=...  and  S2_API_KEY=...   (leave DEBATE_QUEUE_URL unset: debates run inside the backend)

`app/routers/debates_router.py` imports build_fork_info, copy_exists_error, get_user_copy, get_write_target from
`app.project_forking` and uses `app.auth`, `app.database`, `app.models`. Start the backend; an import error names the line to fix.

## First real test
    python scripts/smoke_debate.py --topic "Is X better than Y for Z?" \
      --for-model anthropic/claude-haiku-5.5 --against-model anthropic/claude-haiku-5.5 \
      --judge-model openai/gpt-6-luna --check --max-cost 0.5
