"""Print a user/project/node triple that exists in THIS database, for scripts/debate_client.py.

    python3 scripts/find_ids.py

Reads DATABASE_URL / DB_USER / DB_PASSWORD the same way migrate.py does.
"""
import asyncio
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from migrate import connect_args, load_dotenv  # noqa: E402

SQL = """
SELECT n.created_by_id::text AS user_id, n.project_id::text, n.id::text AS node_id,
       p.name AS project_name, coalesce(n.title, '(untitled)') AS node_title,
       jsonb_array_length(coalesce(n.chats, '[]'::jsonb)) AS messages
FROM nodes n
JOIN projects p ON p.id = n.project_id
WHERE n.node_type = 'standard'
ORDER BY n.created_at DESC NULLS LAST
LIMIT 10
"""


async def main() -> int:
    import asyncpg

    load_dotenv()
    dsn, kwargs, shown = connect_args()
    conn = await asyncpg.connect(dsn, **kwargs)
    try:
        rows = await conn.fetch(SQL)
        if not rows:
            print(f"{shown}: no standard nodes at all. Create a project and a node in the app first.")
            return 1
        print(f"{shown}: {len(rows)} node(s) you can start a debate from\n")
        for r in rows:
            print(f"  project {r['project_name']!r}  node {r['node_title'][:40]!r}  ({r['messages']} messages)")
            print(f"    --user-id {r['user_id']} \\")
            print(f"    --project {r['project_id']} \\")
            print(f"    --node {r['node_id']}")
            print()
        return 0
    finally:
        await conn.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))