-- TEMPLATE, review before running. Not tested against your real roles.
--
-- Row-level security only protects you if the roles the backend and the Lambdas connect as do NOT own the tables
-- and do not have BYPASSRLS. If your backend already connects as such a role, simply reuse that role for the
-- Lambdas (same DB_USER) and only run the GRANTs for the new objects below.

-- Replace tangent_app with your runtime role.
GRANT SELECT, INSERT, UPDATE, DELETE ON debates, debate_events, debate_results TO tangent_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO tangent_app;

-- LangGraph checkpoints (created by `python scripts/setup_db.py --saver`)
GRANT USAGE, CREATE ON SCHEMA langgraph TO tangent_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA langgraph TO tangent_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA langgraph GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO tangent_app;

-- Sanity checks:
--   SELECT rolname, rolsuper, rolbypassrls FROM pg_roles WHERE rolname = 'tangent_app';   -- both must be false
--   SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname LIKE 'debate%';
