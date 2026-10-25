"""One-time database setup, run from your machine (reads DATABASE_URL, DB_USER, DB_PASSWORD from .env).

    python scripts/setup_db.py --ddl      # apply docs/tangent-debate-mode-ddl.sql (tables, enums, RLS, 'debate' node type)
    python scripts/setup_db.py --saver    # create LangGraph's checkpoint tables in the `langgraph` schema
    python scripts/setup_db.py --ddl --saver

Run --ddl ONCE: it is not written to be re-run. If you use a migration tool, put the SQL file in it instead.
The role in DATABASE_URL must be able to CREATE TYPE/TABLE/POLICY (the owner), which is usually NOT the role the
Lambdas and backend run as. See deploy/runtime_grants.sql for the runtime role.
"""
import argparse
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    from dotenv import find_dotenv, load_dotenv

    load_dotenv(find_dotenv(usecwd=True))
except ImportError:
    pass

import psycopg

from debate.pg.checkpointer import setup_saver
from debate.pg.db import normalize_url

DDL = Path(__file__).resolve().parents[1] / "docs" / "tangent-debate-mode-ddl.sql"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--ddl", action="store_true")
    p.add_argument("--saver", action="store_true")
    a = p.parse_args()
    if not (a.ddl or a.saver):
        p.error("choose --ddl and/or --saver")
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL is not set")
    if a.ddl:
        # ALTER TYPE ... ADD VALUE cannot be used in the same transaction as later statements on older servers,
        # so run it on its own connection with autocommit and the rest as one script.
        with psycopg.connect(normalize_url(url), autocommit=True) as conn:
            conn.execute(DDL.read_text())
        print("DDL applied")
    if a.saver:
        asyncio.run(setup_saver(url))
        print("langgraph checkpoint tables created")


if __name__ == "__main__":
    main()
