-- Stand-in for the parts of the existing Tangent schema the debate DDL depends on.
-- Mirrors app/models.py (nodes, trees, node_merge_sources) as of the files you sent.
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE TYPE node_type AS ENUM ('standard', 'temporary');
CREATE TABLE users (id UUID PRIMARY KEY DEFAULT gen_random_uuid(), email TEXT UNIQUE NOT NULL);
CREATE TABLE projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL DEFAULT 'p',
    created_by_id UUID NOT NULL REFERENCES users(id),
    forked_from_project_id UUID REFERENCES projects(id)
);
CREATE TABLE shares (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id),
    shared_by_id UUID NOT NULL REFERENCES users(id),
    shared_with_id UUID NOT NULL REFERENCES users(id),
    permission TEXT NOT NULL DEFAULT 'view',
    revoked_at TIMESTAMPTZ
);
CREATE TABLE trees (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id),
    root_node_id UUID,
    created_by_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE nodes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tree_id UUID NOT NULL REFERENCES trees(id),
    project_id UUID NOT NULL REFERENCES projects(id),
    parent_id UUID REFERENCES nodes(id),
    created_by_id UUID NOT NULL REFERENCES users(id),
    node_type node_type NOT NULL DEFAULT 'standard',
    status TEXT NOT NULL DEFAULT 'active',
    title TEXT,
    summary TEXT,
    chats JSONB NOT NULL DEFAULT '[]'::jsonb,
    fork_index INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_nodes_parent_fork_index UNIQUE (parent_id, fork_index)
);
CREATE TABLE node_merge_sources (
    node_id UUID NOT NULL REFERENCES nodes(id),
    source_leaf_id UUID NOT NULL REFERENCES nodes(id),
    PRIMARY KEY (node_id, source_leaf_id)
);
-- Copied from the live database (pg_policies / pg_proc), so the debate DDL is tested against the real definitions.
CREATE FUNCTION has_project_access(check_project_id uuid) RETURNS boolean LANGUAGE sql STABLE AS $$
    SELECT EXISTS (
        SELECT 1 FROM projects p
        WHERE p.id = check_project_id
          AND p.created_by_id = nullif(current_setting('app.current_user_id', TRUE), '')::uuid
    )
    OR EXISTS (
        SELECT 1 FROM shares s
        WHERE s.project_id = check_project_id
          AND s.shared_with_id = nullif(current_setting('app.current_user_id', TRUE), '')::uuid
          AND s.revoked_at IS NULL
    );
$$;
ALTER TABLE projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE projects FORCE ROW LEVEL SECURITY;
ALTER TABLE nodes ENABLE ROW LEVEL SECURITY;
ALTER TABLE nodes FORCE ROW LEVEL SECURITY;
ALTER TABLE trees ENABLE ROW LEVEL SECURITY;
ALTER TABLE trees FORCE ROW LEVEL SECURITY;
ALTER TABLE shares ENABLE ROW LEVEL SECURITY;
ALTER TABLE shares FORCE ROW LEVEL SECURITY;
ALTER TABLE node_merge_sources ENABLE ROW LEVEL SECURITY;
ALTER TABLE node_merge_sources FORCE ROW LEVEL SECURITY;
CREATE POLICY projects_owner_all ON projects FOR ALL
    USING (created_by_id = nullif(current_setting('app.current_user_id', true), '')::uuid)
    WITH CHECK (created_by_id = nullif(current_setting('app.current_user_id', true), '')::uuid);
CREATE POLICY projects_sharee_select ON projects FOR SELECT USING (EXISTS (
    SELECT 1 FROM shares s WHERE s.project_id = projects.id
      AND s.shared_with_id = nullif(current_setting('app.current_user_id', true), '')::uuid AND s.revoked_at IS NULL));
CREATE POLICY nodes_owner_all ON nodes FOR ALL
    USING (EXISTS (SELECT 1 FROM projects p WHERE p.id = nodes.project_id
        AND p.created_by_id = nullif(current_setting('app.current_user_id', true), '')::uuid))
    WITH CHECK (EXISTS (SELECT 1 FROM projects p WHERE p.id = nodes.project_id
        AND p.created_by_id = nullif(current_setting('app.current_user_id', true), '')::uuid));
CREATE POLICY nodes_sharee_select ON nodes FOR SELECT USING (has_project_access(project_id));
CREATE POLICY trees_owner_all ON trees FOR ALL
    USING (EXISTS (SELECT 1 FROM projects p WHERE p.id = trees.project_id
        AND p.created_by_id = nullif(current_setting('app.current_user_id', true), '')::uuid))
    WITH CHECK (EXISTS (SELECT 1 FROM projects p WHERE p.id = trees.project_id
        AND p.created_by_id = nullif(current_setting('app.current_user_id', true), '')::uuid));
CREATE POLICY trees_sharee_select ON trees FOR SELECT USING (has_project_access(project_id));
-- DIFFERENCE FROM THE LIVE DATABASE: the live shares_select reads projects, and projects_sharee_select reads shares.
-- On Postgres 16 that cycle fails with "infinite recursion detected in policy for relation projects". This version
-- drops the projects lookup: the owner is the one who shared (shared_by_id), so no cycle.
CREATE POLICY shares_select ON shares FOR SELECT USING (
    shared_by_id = nullif(current_setting('app.current_user_id', true), '')::uuid
    OR (shared_with_id = nullif(current_setting('app.current_user_id', true), '')::uuid AND revoked_at IS NULL));
CREATE POLICY node_merge_sources_owner_all ON node_merge_sources FOR ALL
    USING (EXISTS (SELECT 1 FROM nodes n JOIN projects p ON p.id = n.project_id WHERE n.id = node_merge_sources.node_id
        AND p.created_by_id = nullif(current_setting('app.current_user_id', true), '')::uuid))
    WITH CHECK (EXISTS (SELECT 1 FROM nodes n JOIN projects p ON p.id = n.project_id WHERE n.id = node_merge_sources.node_id
        AND p.created_by_id = nullif(current_setting('app.current_user_id', true), '')::uuid));
CREATE POLICY node_merge_sources_sharee_select ON node_merge_sources FOR SELECT
    USING (EXISTS (SELECT 1 FROM nodes n WHERE n.id = node_merge_sources.node_id AND has_project_access(n.project_id)));
