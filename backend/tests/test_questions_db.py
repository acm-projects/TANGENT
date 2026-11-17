"""Question cards against the real DB: a card's chain, answered through the endpoint. Skipped without a database."""
import asyncio
import os
import sys
from uuid import UUID

import pytest
from dotenv import load_dotenv

load_dotenv()
if not (os.getenv("DATABASE_URL") and os.getenv("JWT_SECRET_KEY")):
    pytest.skip("needs DATABASE_URL and JWT_SECRET_KEY (a real database)", allow_module_level=True)

from fastapi.testclient import TestClient

from app import database, questions
from app.agent import tools
from app.main import app
from app.models import Node

sys.path.insert(0, os.path.dirname(__file__))
from test_tree_flow import _workspace_id, cleanup, fresh_pool, google, sign_up  # noqa: E402,F401  (fixtures)


def test_question_chain_through_the_endpoint():
    with TestClient(app) as c:
        auth = sign_up(c)
        me = c.get("/auth/me", headers=auth).json()
        pid = c.post("/projects/", json={"project_name": "Q", "workspace_id": _workspace_id(me["id"])},
                     headers=auth).json()["id"]
        root = c.get(f"/projects/{pid}/tree", headers=auth).json()["tree"]["root_node_id"]

        async def ask():
            async with database.AsyncSessionLocal() as db, db.begin():
                await tools._as_user(db, UUID(me["id"]))
                card = await questions.ask(db, await db.get(Node, UUID(root)), UUID(me["id"]), questions.clean([
                    {"prompt": "Which era?", "options": [{"label": "1970s"}, {"label": "Today"}], "recommended": "Today"},
                    {"prompt": "Which sources?", "type": "multi", "options": [{"label": "Papers"}, {"label": "News"}]},
                ]), {"by": "node", "model": "m", "origin": root})
                return str(card.id)

        first = asyncio.run(ask())
        card = c.get(f"/nodes/{first}", headers=auth).json()
        assert card["node_type"] == "question" and card["question"]["recommended"] == "Today"

        a = c.post(f"/nodes/{first}/answer", json={"answer": "Today"}, headers=auth).json()
        assert not a["final"] and a["node"]["node_type"] == "question" and a["continue_prompt"] is None
        again = c.post(f"/nodes/{first}/answer", json={"answer": "Today"}, headers=auth).json()
        assert again["existing"] and again["node"]["id"] == a["node"]["id"]

        last = c.post(f"/nodes/{a['node']['id']}/answer", json={"answer": ["News", "Papers"]}, headers=auth).json()
        assert last["final"] and last["node"]["node_type"] == "standard"
        assert "Q: Which era?\nA: Today" in last["continue_prompt"] and "A: Papers, News" in last["continue_prompt"]
        tree = c.get(f"/projects/{pid}/tree", headers=auth).json()
        assert len(tree["nodes"]) == 4  # root, two question cards, the branch the research continues in
