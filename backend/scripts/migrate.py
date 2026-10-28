"""Run a plain .sql migration file against the database, so no psql client is needed.

    python3 scripts/migrate.py deploy/migration_branches.sql
    python3 scripts/migrate.py --check

Connects exactly the way the app does: `debate.pg.db.normalize_url` reads DATABASE_URL, strips a
`jdbc:` prefix, fills in DB_USER / DB_PASSWORD when the URL carries no credentials, and adds
sslmode=require for a remote host. Missing variables are loaded from `.env` first, as uvicorn does.

The file is sent as one simple query, so its own BEGIN/COMMIT applies: if any statement fails,
nothing is left half-applied. --check only reports the current state and changes nothing.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

CHECKS = [
    ("debate_results.branches column", """
        SELECT data_type || ' not null=' || (is_nullable = 'NO')::text || ' default=' || coalesce(column_default, '-')
        FROM information_schema.columns
        WHERE table_name = 'debate_results' AND column_name = 'branches'"""),
    ("nodes.branch_of_debate_id column", """
        SELECT data_type FROM information_schema.columns
        WHERE table_name = 'nodes' AND column_name = 'branch_of_debate_id'"""),
    ("nodes_branch_of_debate_id_idx index", """
        SELECT indexname FROM pg_indexes WHERE indexname = 'nodes_branch_of_debate_id_idx'"""),
    ("debate_results RLS policies", """
        SELECT string_agg(cmd, ', ' ORDER BY cmd) FROM pg_policies WHERE tablename = 'debate_results'"""),
]


def load_dotenv(path: str = ".env") -> None:
    """Fill in anything the shell has not already exported. Real environment wins, as with uvicorn."""
    env = pathlib.Path(path)
    if not env.exists():
        return
    for line in env.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def connect_args() -> tuple[str, dict, str]:
    """Returns (dsn, kwargs for asyncpg.connect, a host/db string safe to print)."""
    from sqlalchemy.engine import make_url

    from debate.pg.db import normalize_url

    raw = os.environ.get("DATABASE_URL", "")
    if not raw:
        sys.exit("DATABASE_URL is not set, and .env has no DATABASE_URL line.")

    url = make_url(normalize_url(raw))
    if not url.username:
        sys.exit("DATABASE_URL carries no username, and DB_USER is not set in the environment or in .env.\n"
                 "Either put credentials in the URL (postgresql://user:password@host:5432/dbname) or set\n"
                 "DB_USER and DB_PASSWORD, which is what app/database.py uses.")

    # asyncpg takes ssl= as an argument rather than sslmode= in the DSN.
    query = dict(url.query)
    sslmode = query.pop("sslmode", None) or query.pop("ssl", None)
    kwargs: dict = {"statement_cache_size": 0}
    if sslmode in ("require", "verify-ca", "verify-full", "prefer", "allow", "true"):
        kwargs["ssl"] = "require"
    url = url.set(query=query)
    return url.render_as_string(hide_password=False), kwargs, f"{url.username}@{url.host}/{url.database}"


TREE_SQL = """
SELECT n.id::text, n.node_type::text, n.title, n.fork_index,
       n.branch_of_debate_id IS NOT NULL AS from_debate,
       jsonb_array_length(coalesce(n.chats, '[]'::jsonb)) AS messages
FROM nodes n
WHERE n.id = $1 OR n.parent_id = $1
ORDER BY (n.id = $1) DESC, n.fork_index"""

SEEDS_SQL = """
SELECT n.id::text, n.title, n.chats
FROM nodes n WHERE n.parent_id = $1 AND n.branch_of_debate_id IS NOT NULL
ORDER BY n.fork_index"""


async def show_tree(conn, origin: str) -> int:
    """What step 4 of the runbook checks: the branch nodes are siblings of the debate node, and no branch's
    seeded context mentions another branch's subject."""
    rows = await conn.fetch(TREE_SQL, origin)
    if not rows:
        print(f"no node {origin}, and nothing parented to it")
        return 1

    print(f"children of {origin}:\n")
    print(f"  {'node':38}  {'type':10}  {'msgs':>4}  {'from debate':11}  title")
    for r in rows:
        tag = "(origin) " if r["id"] == origin else ""
        print(f"  {r['id']:38}  {r['node_type']:10}  {r['messages']:>4}  "
              f"{str(bool(r['from_debate'])):11}  {tag}{(r['title'] or '')[:46]}")

    branches = await conn.fetch(SEEDS_SQL, origin)
    if not branches:
        print("\nno branch nodes under this node yet")
        return 0

    print(f"\nisolation check across {len(branches)} branch node(s):")
    ok = True
    for row in branches:
        chats = row["chats"]
        if isinstance(chats, str):
            import json
            chats = json.loads(chats)
        seed = "\n".join(str(m.get("content", "")) for m in (chats or []))
        leaked = [o["title"] for o in branches if o["id"] != row["id"] and (o["title"] or "@@") in seed]
        ok &= not leaked
        print(f"  {'PASS' if not leaked else 'FAIL'}  {(row['title'] or '')[:44]:44} "
              f"{len(seed):>6} chars" + (f"   <- mentions {leaked}" if leaked else ""))
    print("\nno branch can see a sibling's subject" if ok else "\na sibling subject leaked into a seed")
    return 0 if ok else 1


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("sql_file", nargs="?", default="deploy/migration_branches.sql")
    ap.add_argument("--check", action="store_true", help="report the current state only; apply nothing")
    ap.add_argument("--tree", metavar="NODE_ID",
                    help="show that node and its children, and check branch isolation; applies nothing")
    ap.add_argument("--env", default=".env", help="file to read missing variables from (default .env)")
    args = ap.parse_args()

    try:
        import asyncpg
    except ImportError:
        return int(bool(sys.stderr.write("asyncpg is not installed: pip install asyncpg\n")))

    load_dotenv(args.env)
    dsn, kwargs, shown = connect_args()

    conn = await asyncpg.connect(dsn, **kwargs)
    try:
        if args.tree:
            return await show_tree(conn, args.tree)

        if not args.check:
            path = pathlib.Path(args.sql_file)
            if not path.exists():
                return int(bool(sys.stderr.write(f"no such file: {path}\n")))
            print(f"applying {path} to {shown}")
            await conn.execute(path.read_text())  # one simple query, so the file's BEGIN/COMMIT holds
            print("applied (safe to run again)\n")

        print(f"state of {shown}:")
        ok = True
        for label, sql in CHECKS:
            got = await conn.fetchval(sql)
            if label.endswith("policies"):
                have = set((got or "").replace(" ", "").split(","))
                good = {"INSERT", "SELECT", "UPDATE"} <= have
                ok &= good
                print(f"  {'PASS' if good else 'FAIL'}  {label}: {got or 'none'}"
                      + ("" if good else "   <- UPDATE missing; every branch write would fail closed under RLS"))
            else:
                ok &= got is not None
                print(f"  {'PASS' if got else 'FAIL'}  {label}: {got or 'missing'}")
        print("\nall good" if ok else "\nsomething is missing above")
        return 0 if ok else 1
    finally:
        await conn.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))