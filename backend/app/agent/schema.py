"""Tables of the agent orchestration runtime. database.ensure_columns runs these at startup (idempotent);
backend/migrations/2026-11-agent-runs.sql is the same DDL for databases where the app role has no DDL rights.
No row-level security (like the papers tables): the router only hands a run to the user who started it."""

AGENT_DDL = [
    """CREATE TABLE IF NOT EXISTS agent_runs (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        project_id uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        model text NOT NULL,
        goal text NOT NULL,                      -- immutable: the original objective
        active_node_id uuid,
        status text NOT NULL DEFAULT 'queued',   -- queued | running | waiting_input | completed | failed | cancelled
        outcome text,                            -- satisfied | partially_satisfied | inconclusive | blocked
        final jsonb,
        pending_input jsonb,
        clarifications jsonb NOT NULL DEFAULT '[]'::jsonb,
        authorized_deletes jsonb NOT NULL DEFAULT '[]'::jsonb,
        plan_version int NOT NULL DEFAULT 0,
        iteration int NOT NULL DEFAULT 0,
        tool_calls int NOT NULL DEFAULT 0,
        replans int NOT NULL DEFAULT 0,
        invalid_streak int NOT NULL DEFAULT 0,
        locked_at timestamptz,                   -- lease: a 'running' run whose lock is stale lost its worker
        error text,
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now()
    )""",
    "CREATE INDEX IF NOT EXISTS agent_runs_claim_idx ON agent_runs (created_at) WHERE status IN ('queued', 'running')",
    # one live run per project
    "CREATE UNIQUE INDEX IF NOT EXISTS agent_runs_one_live_idx ON agent_runs (project_id) "
    "WHERE status IN ('queued', 'running', 'waiting_input')",
    """CREATE TABLE IF NOT EXISTS agent_plans (
        run_id uuid NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
        version int NOT NULL,
        strategy text NOT NULL,
        assumptions jsonb NOT NULL DEFAULT '[]'::jsonb,
        reason text,
        created_at timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (run_id, version)
    )""",
    """CREATE TABLE IF NOT EXISTS agent_tasks (
        run_id uuid NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
        key text NOT NULL,                       -- t1, t2, ...: unique within the run
        objective text NOT NULL,
        status text NOT NULL DEFAULT 'pending',  -- pending | in_progress | completed | skipped | failed | blocked
        depends_on jsonb NOT NULL DEFAULT '[]'::jsonb,
        plan_version int NOT NULL,
        assessment jsonb,
        reason text,
        created_at timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (run_id, key)
    )""",
    # Written before a tool runs and finished after it: what recovery and the evidence check read.
    """CREATE TABLE IF NOT EXISTS agent_executions (
        id bigserial PRIMARY KEY,
        run_id uuid NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
        iteration int NOT NULL,
        call_index int NOT NULL,
        kind text NOT NULL,                      -- op | tool
        task_key text,
        name text NOT NULL,
        args jsonb NOT NULL DEFAULT '{}'::jsonb,
        idempotency_key text NOT NULL,
        status text NOT NULL DEFAULT 'started',  -- started | succeeded | failed | unknown
        result jsonb,
        started_at timestamptz NOT NULL DEFAULT now(),
        finished_at timestamptz,
        UNIQUE (run_id, idempotency_key)
    )""",
    "CREATE INDEX IF NOT EXISTS agent_executions_run_idx ON agent_executions (run_id, id)",
    """CREATE TABLE IF NOT EXISTS agent_llm_calls (
        id bigserial PRIMARY KEY,
        run_id uuid NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
        iteration int NOT NULL,
        attempt int NOT NULL DEFAULT 1,
        model text,
        messages jsonb NOT NULL,
        response jsonb,
        usage jsonb,
        error text,
        duration_ms int,
        created_at timestamptz NOT NULL DEFAULT now()
    )""",
    "CREATE INDEX IF NOT EXISTS agent_llm_calls_run_idx ON agent_llm_calls (run_id, id)",
    """CREATE TABLE IF NOT EXISTS agent_events (
        id bigserial PRIMARY KEY,
        run_id uuid NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
        type text NOT NULL,
        event_key text,
        payload jsonb NOT NULL DEFAULT '{}'::jsonb,
        created_at timestamptz NOT NULL DEFAULT now()
    )""",
    "CREATE INDEX IF NOT EXISTS agent_events_run_idx ON agent_events (run_id, id)",
    "CREATE UNIQUE INDEX IF NOT EXISTS agent_events_key_idx ON agent_events (run_id, event_key) WHERE event_key IS NOT NULL",
]
