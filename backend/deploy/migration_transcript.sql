-- Keep the debate itself, not just its verdict.
-- Safe to run more than once. Run it before deploying the code that writes `transcript`.

BEGIN;

-- debate_events holds one row per streamed token and is purged a few minutes after a debate ends, so the arguments
-- themselves used to survive only while the stream was warm. A node opened the next day showed a verdict with nothing
-- behind it. The transcript is bounded (one record per turn, ~10-20 per debate) so it belongs on the result row.
ALTER TABLE debate_results
    ADD COLUMN IF NOT EXISTS transcript jsonb NOT NULL DEFAULT '[]'::jsonb;

COMMENT ON COLUMN debate_results.transcript IS
    'The debate in full, in order: [{side,phase,round,thinking,argument,claims,truncated}]. Kept for the life of the '
    'node. Claims are kept because branches reference claim ids in from_claims.';

COMMIT;
