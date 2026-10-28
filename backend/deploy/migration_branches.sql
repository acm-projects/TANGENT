-- Branch directions on a debate result, and the nodes made from them.
-- Safe to run more than once. Run it before deploying the code that writes `branches`.

BEGIN;

-- Why jsonb and not a table: a branch is read and written only as part of its result, never queried across debates,
-- and the shape will keep changing while Gent is built. One migration now, no more later.
ALTER TABLE debate_results
    ADD COLUMN IF NOT EXISTS branches jsonb NOT NULL DEFAULT '[]'::jsonb;

COMMENT ON COLUMN debate_results.branches IS
    'Questions worth exploring next: [{id,title,question,why,kind,from_claims,selected,created_node_id}]. '
    'Each selected branch becomes a node whose parent is the node the debate started from, never the debate node.';

-- Branch nodes are ordinary nodes; this marks where one came from so the map can trace it back to its debate.
ALTER TABLE nodes
    ADD COLUMN IF NOT EXISTS branch_of_debate_id uuid REFERENCES debates(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS nodes_branch_of_debate_id_idx
    ON nodes (branch_of_debate_id) WHERE branch_of_debate_id IS NOT NULL;

-- Ticking a branch and recording the node it produced are UPDATEs on an existing row. debate_results had only
-- SELECT and INSERT policies, so without this every branch write fails closed under RLS.
DROP POLICY IF EXISTS debate_results_update_owner ON debate_results;
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

-- Check:
--   \d debate_results
--   SELECT node_id, jsonb_array_length(branches) AS n FROM debate_results ORDER BY created_at DESC LIMIT 5;
