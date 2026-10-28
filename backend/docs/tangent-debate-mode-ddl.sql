ALTER TYPE node_type ADD VALUE IF NOT EXISTS 'debate';

BEGIN;

CREATE SCHEMA IF NOT EXISTS langgraph;

CREATE TYPE debate_status AS ENUM (
    'queued',
    'running',
    'awaiting_input',
    'finalizing',
    'completed',
    'failed',
    'cancelled'
);

CREATE TYPE debate_winner AS ENUM ('for', 'against', 'no_clear_winner');

CREATE TYPE debate_end_reason AS ENUM (
    'rounds_exhausted',
    'budget_exhausted',
    'user_picked',
    'user_stopped'
);

CREATE TYPE debate_phase AS ENUM (
    'intake',
    'frame',
    'research',
    'opening',
    'rebuttal',
    'closing',
    'judging'
);

CREATE TYPE debate_event_type AS ENUM (
    'phase_changed',
    'question_requested',
    'answer_received',
    'turn_started',
    'turn_completed',
    'thinking',
    'control_applied',
    'tool_called',
    'verdict_ready',
    'completed',
    'failed',
    'cancelled',
    'token'
);
-- Existing database: ALTER TYPE debate_event_type ADD VALUE IF NOT EXISTS 'token';

CREATE TABLE debates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    owner_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    parent_node_id UUID REFERENCES nodes(id) ON DELETE SET NULL,
    topic TEXT NOT NULL,
    for_model TEXT NOT NULL,
    against_model TEXT NOT NULL,
    judge_model TEXT NOT NULL,
    rounds SMALLINT NOT NULL DEFAULT 2 CHECK (rounds BETWEEN 1 AND 3),
    status debate_status NOT NULL DEFAULT 'queued',
    current_phase debate_phase,
    current_round SMALLINT NOT NULL DEFAULT 0,
    pending_questions JSONB,
    resume_payload JSONB,
    result_node_id UUID REFERENCES nodes(id) ON DELETE SET NULL,
    retain_artifacts BOOLEAN NOT NULL DEFAULT FALSE,
    end_reason debate_end_reason,
    control JSONB,
    lease_until TIMESTAMPTZ,
    error_code TEXT,
    cost_usd NUMERIC(12, 6) NOT NULL DEFAULT 0,
    usage_summary JSONB,
    wall_ms INTEGER,
    active_ms INTEGER NOT NULL DEFAULT 0,
    waited_ms INTEGER,
    segments JSONB NOT NULL DEFAULT '[]'::jsonb,
    timings JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL DEFAULT NOW() + INTERVAL '7 days',
    completed_at TIMESTAMPTZ,
    CONSTRAINT ck_debates_pending_only_when_awaiting
        CHECK (status = 'awaiting_input' OR pending_questions IS NULL),
    CONSTRAINT ck_debates_timings_is_array
        CHECK (jsonb_typeof(timings) = 'array'),
    CONSTRAINT ck_debates_segments_is_array
        CHECK (jsonb_typeof(segments) = 'array')
);

CREATE INDEX ix_debates_project_id ON debates (project_id);
CREATE INDEX ix_debates_owner_id ON debates (owner_id);
CREATE INDEX ix_debates_parent_node_id ON debates (parent_node_id) WHERE parent_node_id IS NOT NULL;
CREATE INDEX ix_debates_owner_active ON debates (owner_id)
    WHERE status IN ('queued', 'running', 'awaiting_input', 'finalizing');
CREATE INDEX ix_debates_expiry ON debates (expires_at)
    WHERE status IN ('queued', 'running', 'awaiting_input');
CREATE UNIQUE INDEX uq_debates_result_node ON debates (result_node_id)
    WHERE result_node_id IS NOT NULL;

CREATE TABLE debate_events (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    debate_id UUID NOT NULL REFERENCES debates(id) ON DELETE CASCADE,
    event_type debate_event_type NOT NULL,
    event_key TEXT,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX ix_debate_events_debate_id_id ON debate_events (debate_id, id);
CREATE UNIQUE INDEX uq_debate_events_key ON debate_events (debate_id, event_key)
    WHERE event_key IS NOT NULL;

CREATE TABLE debate_results (
    node_id UUID PRIMARY KEY REFERENCES nodes(id) ON DELETE CASCADE,
    debate_id UUID UNIQUE REFERENCES debates(id) ON DELETE SET NULL,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    proposition TEXT NOT NULL,
    winner debate_winner NOT NULL,
    judge_would_have_chosen debate_winner,
    confidence NUMERIC(3, 2) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    summary TEXT NOT NULL,
    final_output TEXT NOT NULL,
    verdict_rationale TEXT NOT NULL,
    scores JSONB NOT NULL,
    strongest_counterpoints JSONB NOT NULL DEFAULT '[]'::jsonb,
    verdict_flips_if JSONB NOT NULL DEFAULT '[]'::jsonb,
    citations JSONB NOT NULL DEFAULT '[]'::jsonb,
    clarifications JSONB NOT NULL DEFAULT '[]'::jsonb,
    for_model TEXT NOT NULL,
    against_model TEXT NOT NULL,
    judge_model TEXT NOT NULL,
    rounds SMALLINT NOT NULL,
    end_reason debate_end_reason NOT NULL DEFAULT 'rounds_exhausted',
    cost_usd NUMERIC(12, 6) NOT NULL DEFAULT 0,
    usage JSONB NOT NULL DEFAULT '[]'::jsonb,
    usage_summary JSONB,
    timings JSONB NOT NULL DEFAULT '[]'::jsonb,
    timing_summary JSONB,
    wall_ms INTEGER,
    active_ms INTEGER,
    waited_ms INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_debate_results_usage_is_array CHECK (jsonb_typeof(usage) = 'array'),
    CONSTRAINT ck_debate_results_timings_is_array CHECK (jsonb_typeof(timings) = 'array')
);

CREATE INDEX ix_debate_results_project_id ON debate_results (project_id);

ALTER TABLE debates ENABLE ROW LEVEL SECURITY;
ALTER TABLE debates FORCE ROW LEVEL SECURITY;
ALTER TABLE debate_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE debate_events FORCE ROW LEVEL SECURITY;
ALTER TABLE debate_results ENABLE ROW LEVEL SECURITY;
ALTER TABLE debate_results FORCE ROW LEVEL SECURITY;

CREATE POLICY debates_select_owner ON debates
    FOR SELECT
    USING (owner_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid);

CREATE POLICY debates_insert_owner ON debates
    FOR INSERT
    WITH CHECK (
        owner_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid
        AND EXISTS (
            SELECT 1 FROM projects p
            WHERE p.id = debates.project_id
              AND p.created_by_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid
        )
    );

CREATE POLICY debates_update_owner ON debates
    FOR UPDATE
    USING (owner_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid)
    WITH CHECK (owner_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid);

CREATE POLICY debates_select_maintenance ON debates
    FOR SELECT
    USING (current_setting('app.system_job', true) = 'debate_maintenance');

CREATE POLICY debates_update_maintenance ON debates
    FOR UPDATE
    USING (current_setting('app.system_job', true) = 'debate_maintenance')
    WITH CHECK (current_setting('app.system_job', true) = 'debate_maintenance');

CREATE POLICY debate_events_select_owner ON debate_events
    FOR SELECT
    USING (EXISTS (
        SELECT 1 FROM debates d
        WHERE d.id = debate_events.debate_id
          AND d.owner_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid
    ));

CREATE POLICY debate_events_insert_owner ON debate_events
    FOR INSERT
    WITH CHECK (EXISTS (
        SELECT 1 FROM debates d
        WHERE d.id = debate_events.debate_id
          AND d.owner_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid
    ));

CREATE POLICY debate_events_delete_owner ON debate_events
    FOR DELETE
    USING (EXISTS (
        SELECT 1 FROM debates d
        WHERE d.id = debate_events.debate_id
          AND d.owner_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid
    ));

CREATE POLICY debate_events_select_maintenance ON debate_events
    FOR SELECT
    USING (current_setting('app.system_job', true) = 'debate_maintenance');

CREATE POLICY debate_events_delete_maintenance ON debate_events
    FOR DELETE
    USING (current_setting('app.system_job', true) = 'debate_maintenance');

-- Readable by whoever can open the project (owner or active sharee), using the same has_project_access() that
-- nodes_sharee_select and trees_sharee_select use, so debates follow any future change to what "access" means.
CREATE POLICY debate_results_select_access ON debate_results
    FOR SELECT
    USING (has_project_access(project_id));

CREATE POLICY debate_results_insert_owner ON debate_results
    FOR INSERT
    WITH CHECK (EXISTS (
        SELECT 1 FROM projects p
        WHERE p.id = debate_results.project_id
          AND p.created_by_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid
    ));

-- Branch directions: the questions a finished debate proposes for exploring next.
ALTER TABLE debate_results ADD COLUMN IF NOT EXISTS branches jsonb NOT NULL DEFAULT '[]'::jsonb;

COMMENT ON COLUMN debate_results.branches IS
    'Questions worth exploring next: [{id,title,question,why,kind,from_claims,selected,created_node_id}]. '
    'A selected branch becomes a node whose parent is the node the debate started from, never the debate node, '
    'so sibling branches never share a lineage and cannot see each other.';

-- Marks a node as having come from a debate, so the map can trace it back. Nullable: ordinary nodes have none.
ALTER TABLE nodes ADD COLUMN IF NOT EXISTS branch_of_debate_id uuid REFERENCES debates(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS nodes_branch_of_debate_id_idx
    ON nodes (branch_of_debate_id) WHERE branch_of_debate_id IS NOT NULL;

-- Ticking a branch and recording the node it produced are UPDATEs on an existing row. Without this policy every
-- branch write fails closed under RLS, so it must exist wherever `branches` does.
CREATE POLICY debate_results_update_owner ON debate_results
    FOR UPDATE
    USING (EXISTS (
        SELECT 1 FROM projects p
        WHERE p.id = debate_results.project_id
          AND p.created_by_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid
    ))
    WITH CHECK (EXISTS (
        SELECT 1 FROM projects p
        WHERE p.id = debate_results.project_id
          AND p.created_by_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid
    ));

COMMIT;
