-- STEP 1: check. Run as the SAME database user your backend uses, in a scratch transaction.
-- Replace the uuid with any real user id. If STEP 1 returns a number, you do not need STEP 2.
-- If it fails with: infinite recursion detected in policy for relation "projects", run STEP 2.
BEGIN;
SELECT set_config('app.current_user_id', '00000000-0000-0000-0000-000000000000', true);
SELECT count(*) FROM projects;
SELECT count(*) FROM shares;
ROLLBACK;

-- STEP 2: fix (only if STEP 1 failed). projects_sharee_select reads shares and shares_select reads projects, which is a
-- cycle. The owner of a share row is the person who shared it (shared_by_id), so the projects lookup is not needed.
-- Behaviour is the same: owner sees every share of their project, a sharee sees their own active share.
BEGIN;
DROP POLICY shares_select ON shares;
CREATE POLICY shares_select ON shares FOR SELECT USING (
    shared_by_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid
    OR (shared_with_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid AND revoked_at IS NULL)
);
COMMIT;
-- Then repeat STEP 1.
