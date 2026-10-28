BEGIN;

LOCK TABLE nodes, node_merge_sources IN ACCESS EXCLUSIVE MODE;

DO $$
DECLARE
    source_att smallint;
BEGIN
    SELECT attnum INTO source_att
    FROM pg_attribute
    WHERE attrelid = 'node_merge_sources'::regclass AND attname = 'source_leaf_id' AND NOT attisdropped;

    IF EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conrelid = 'node_merge_sources'::regclass
          AND confrelid = 'nodes'::regclass
          AND confdeltype = 'a'
          AND source_att = ANY(conkey)
    ) THEN
        RAISE EXCEPTION 'Merge DAG migration was already applied';
    END IF;
END $$;

WITH RECURSIVE merge_cards AS (
    SELECT n.id
    FROM nodes n
    WHERE EXISTS (SELECT 1 FROM node_merge_sources ms WHERE ms.node_id = n.id)
       OR EXISTS (
            SELECT 1
            FROM jsonb_array_elements(
                CASE WHEN jsonb_typeof(n.chats) = 'array' THEN n.chats ELSE '[]'::jsonb END
            ) AS message(value)
            WHERE message.value ? 'branch_source'
              AND message.value ->> 'branch_source' IS NOT NULL
       )
), invalid_merges AS (
    SELECT cards.id
    FROM merge_cards cards
    LEFT JOIN node_merge_sources ms ON ms.node_id = cards.id
    LEFT JOIN nodes source ON source.id = ms.source_leaf_id
    GROUP BY cards.id
    HAVING COUNT(DISTINCT source.id) < 2
), doomed(id) AS (
    SELECT id FROM invalid_merges
    UNION
    SELECT edge.child
    FROM doomed d
    JOIN (
        SELECT id AS child, parent_id AS parent FROM nodes WHERE parent_id IS NOT NULL
        UNION ALL
        SELECT node_id, source_leaf_id FROM node_merge_sources
    ) edge ON edge.parent = d.id
)
DELETE FROM nodes WHERE id IN (SELECT id FROM doomed);

DO $$
DECLARE
    merge_id uuid;
    first_source uuid;
    next_fork_index integer;
BEGIN
    FOR merge_id IN
        SELECT n.id
        FROM nodes n
        WHERE EXISTS (SELECT 1 FROM node_merge_sources ms WHERE ms.node_id = n.id)
        ORDER BY n.created_at, n.id
    LOOP
        SELECT ms.source_leaf_id INTO first_source
        FROM node_merge_sources ms
        JOIN nodes source ON source.id = ms.source_leaf_id
        WHERE ms.node_id = merge_id
        ORDER BY source.created_at, source.id
        LIMIT 1;

        SELECT COALESCE(MAX(fork_index), 0) + 1 INTO next_fork_index
        FROM nodes
        WHERE parent_id = first_source AND id <> merge_id;

        UPDATE nodes
        SET parent_id = first_source, fork_index = next_fork_index
        WHERE id = merge_id;
    END LOOP;
END $$;

UPDATE nodes n
SET chats = COALESCE(
    (
        SELECT jsonb_agg(
            (kept.value - 'branch_source') || jsonb_build_object('seq', kept.seq)
            ORDER BY kept.ordinality
        )
        FROM (
            SELECT message.value, message.ordinality,
                   row_number() OVER (ORDER BY message.ordinality) - 1 AS seq
            FROM jsonb_array_elements(
                CASE WHEN jsonb_typeof(n.chats) = 'array' THEN n.chats ELSE '[]'::jsonb END
            ) WITH ORDINALITY AS message(value, ordinality)
            WHERE message.value ->> 'branch_source' IS NULL
        ) kept
    ),
    '[]'::jsonb
);

DO $$
DECLARE
    source_att smallint;
    fk record;
BEGIN
    SELECT attnum INTO source_att
    FROM pg_attribute
    WHERE attrelid = 'node_merge_sources'::regclass AND attname = 'source_leaf_id' AND NOT attisdropped;

    FOR fk IN
        SELECT conname
        FROM pg_constraint
        WHERE conrelid = 'node_merge_sources'::regclass
          AND confrelid = 'nodes'::regclass
          AND source_att = ANY(conkey)
    LOOP
        EXECUTE format('ALTER TABLE node_merge_sources DROP CONSTRAINT %I', fk.conname);
    END LOOP;

    ALTER TABLE node_merge_sources
        ADD CONSTRAINT node_merge_sources_source_leaf_id_fkey
        FOREIGN KEY (source_leaf_id) REFERENCES nodes(id) ON DELETE NO ACTION;
END $$;

SET CONSTRAINTS ALL IMMEDIATE;
COMMIT;
