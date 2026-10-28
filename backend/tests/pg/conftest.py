import os
import pathlib
import uuid

import psycopg
import pytest

from debate.pg.db import make_engine, make_factory

ADMIN = os.environ.get("TEST_PG_ADMIN_URL")
HERE = pathlib.Path(__file__).parent
DDL = HERE.parent.parent / "docs" / "tangent-debate-mode-ddl.sql"
APP_PW = "app-pw"


def pytest_collection_modifyitems(config, items):
    if ADMIN:
        return
    skip = pytest.mark.skip(reason="set TEST_PG_ADMIN_URL (a superuser URL to a scratch Postgres) to run these")
    for item in items:
        if "tests/pg" in str(item.fspath):
            item.add_marker(skip)


def _with_db(url: str, db: str) -> str:
    head, _, _ = url.rpartition("/")
    return f"{head}/{db}"


@pytest.fixture()
def pg():
    name = "tangent_t_" + uuid.uuid4().hex[:10]
    with psycopg.connect(ADMIN, autocommit=True) as c:
        c.execute(f"CREATE DATABASE {name}")
    admin_url = _with_db(ADMIN, name)
    with psycopg.connect(admin_url, autocommit=True) as c:
        c.execute((HERE / "base_schema.sql").read_text())
        c.execute(DDL.read_text())
        c.execute(f"CREATE ROLE {name}_app LOGIN PASSWORD '{APP_PW}'")
        c.execute(f"GRANT USAGE ON SCHEMA public, langgraph TO {name}_app")
        c.execute(f"GRANT CREATE ON SCHEMA langgraph TO {name}_app")
        c.execute(f"GRANT ALL ON ALL TABLES IN SCHEMA public TO {name}_app")
        c.execute(f"GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO {name}_app")
    host = admin_url.split("@")[-1]
    app_url = f"postgresql://{name}_app:{APP_PW}@{host}"
    env = type("PG", (), {})()
    env.admin_url, env.app_url, env.name = admin_url, app_url, name
    env.engine = make_engine(app_url)
    env.factory = make_factory(env.engine)

    def sql(q, params=None):
        with psycopg.connect(admin_url, autocommit=True) as c:
            cur = c.execute(q, params)
            return cur.fetchall() if cur.description else None

    env.sql = sql
    yield env
    with psycopg.connect(ADMIN, autocommit=True) as c:
        c.execute(f"DROP DATABASE {name} WITH (FORCE)")
        c.execute(f"DROP ROLE IF EXISTS {name}_app")


def seed(pg, n_nodes=3):
    """user, project, tree and a straight chain of nodes. Returns ids."""
    uid = pg.sql("INSERT INTO users (email) VALUES (%s) RETURNING id", (f"{uuid.uuid4().hex[:6]}@x.test",))[0][0]
    pid = pg.sql("INSERT INTO projects (created_by_id) VALUES (%s) RETURNING id", (uid,))[0][0]
    tid = pg.sql("INSERT INTO trees (project_id) VALUES (%s) RETURNING id", (pid,))[0][0]
    nodes, parent = [], None
    for i in range(n_nodes):
        chats = '[{"role":"user","content":"question %d"},{"role":"assistant","content":"answer %d"}]' % (i, i)
        nid = pg.sql(
            "INSERT INTO nodes (tree_id, project_id, parent_id, created_by_id, chats, fork_index, created_at) "
            "VALUES (%s,%s,%s,%s,%s::jsonb, %s, now() + %s * interval '1 second') RETURNING id",
            (tid, pid, parent, uid, chats, i, i),
        )[0][0]
        nodes.append(str(nid))
        parent = nid
    return {"user": str(uid), "project": str(pid), "tree": str(tid), "nodes": nodes}
