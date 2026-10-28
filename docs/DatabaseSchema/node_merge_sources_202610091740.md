| Column | Type | Constraints |
|---|---|---|
| `node_id` | `uuid` | Primary-key part; foreign key to `nodes.id` with `ON DELETE CASCADE` |
| `source_leaf_id` | `uuid` | Primary-key part; foreign key to `nodes.id` with `ON DELETE NO ACTION` |
| `created_at` | `timestamptz` | `NOT NULL`, defaults to `now()` |

Each row identifies one parent of a merge card. A card is a merge iff it has
rows here. Its `parent_id` must equal its first source; the other sources are
ordered by UUID after that first parent in API responses. A source can feed at
most one active merge because only leaves may be merged.

The source foreign key deliberately uses `NO ACTION`: deleting a source without
also deleting merge dependants must fail. `backend/migrations/2026-10-merge-as-dag.sql`
converts the prior snapshot model and changes the constraint. Before running
it, the DB owner should confirm that project members can read this table under
RLS. The existing primary-key index covers `node_id`; the unique index on
`nodes(parent_id, fork_index)` covers `nodes(parent_id)`.
