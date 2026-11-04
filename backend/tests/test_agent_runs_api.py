"""HTTP layer of the agent runtime with the store faked (runs in CI, no secrets): status codes, ownership, the SSE frame
format and replay cursor. The rules and the loop are covered by test_agent_ops.py and tests/pg/test_agent_runtime.py."""
import os
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

_dummies = {"DATABASE_URL": "postgresql://dummy@localhost/dummy", "JWT_SECRET_KEY": "test-secret"}
_added = [k for k in _dummies if k not in os.environ]
os.environ.update({k: _dummies[k] for k in _added})

from fastapi.testclient import TestClient  # noqa: E402

from app.agent import runs_router, store  # noqa: E402
from app.auth import get_current_user  # noqa: E402
from app.database import get_db_session  # noqa: E402
from app.main import app  # noqa: E402

for _k in _added:
    del os.environ[_k]

PROJECT, RUN = uuid.uuid4(), uuid.uuid4()
USER = SimpleNamespace(id=uuid.uuid4())
URL = f"/projects/{PROJECT}/agent/runs"
NOW = datetime(2026, 11, 4, tzinfo=timezone.utc)


@pytest.fixture
def api(monkeypatch):
    calls = {"created": [], "answers": [], "after": []}
    state = {"run": {"run": {"id": str(RUN), "status": "queued"}, "plan": None, "tasks": []}, "events": [], "status": "running"}

    class NoDb:
        async def rollback(self):
            pass

    async def no_db():
        yield NoDb()

    async def require_owner(db, project_id, user):
        return None

    async def get_run(run_id, project_id, user_id):
        return state["run"] if run_id == str(RUN) and user_id == str(USER.id) else None

    async def create_run(project_id, user_id, model, goal, node):
        calls["created"].append((goal, model))
        if state.get("live"):
            raise store.ActiveRunExists()
        return str(RUN)

    async def submit_answer(run_id, answers):
        calls["answers"].append(answers)
        if answers.get("bad"):
            raise store.AnswerError("choose from the options")

    async def read_events(run_id, after, limit=200):
        calls["after"].append(after)
        evs = [e for e in state["events"] if e["id"] > after]
        return evs, state["status"]

    app.dependency_overrides[get_current_user] = lambda: USER
    app.dependency_overrides[get_db_session] = no_db
    monkeypatch.setattr(runs_router, "require_owner", require_owner)
    for fn in (get_run, create_run, submit_answer, read_events):
        monkeypatch.setattr(runs_router.store, fn.__name__, fn)
    with TestClient(app) as c:
        yield c, state, calls
    app.dependency_overrides.clear()


def test_create_returns_the_run(api):
    c, state, calls = api
    r = c.post(URL, json={"goal": "Does RL help?"})
    assert r.status_code == 201 and r.json()["run"]["id"] == str(RUN)
    assert calls["created"][0][0] == "Does RL help?"


def test_create_validates_goal_and_model_and_allows_one_live_run(api):
    c, state, calls = api
    assert c.post(URL, json={"goal": "hi"}).status_code == 422
    assert c.post(URL, json={"goal": "A real goal here", "model": "no/such-model"}).status_code == 400
    state["live"] = True
    assert c.post(URL, json={"goal": "A real goal here"}).status_code == 409


def test_a_run_is_only_visible_to_its_user(api):
    c, *_ = api
    assert c.get(f"{URL}/{RUN}").status_code == 200
    assert c.get(f"{URL}/{uuid.uuid4()}").status_code == 404
    assert c.post(f"{URL}/{uuid.uuid4()}/cancel").status_code == 404
    assert c.get(f"{URL}/{uuid.uuid4()}/events").status_code == 404


def test_answer_maps_bad_answers_to_422(api):
    c, state, calls = api
    assert c.post(f"{URL}/{RUN}/answer", json={"answers": {"scope": "No", "pick": ["a", "b"]}}).status_code == 200
    assert calls["answers"][0] == {"scope": "No", "pick": ["a", "b"]}
    r = c.post(f"{URL}/{RUN}/answer", json={"answers": {"bad": "x"}})
    assert r.status_code == 422 and r.json()["detail"] == "choose from the options"


def test_events_stream_frames_resume_from_the_cursor_and_end_with_done(api):
    c, state, calls = api
    state["events"] = [{"id": i, "type": t, "payload": {"n": i}, "created_at": NOW}
                       for i, t in ((1, "run.created"), (2, "plan.created"), (3, "run.completed"))]
    state["status"] = "completed"
    full = c.get(f"{URL}/{RUN}/events").text
    assert full.startswith("id: 1\nevent: run.created\ndata: ")
    assert full.count("event: ") == 4 and full.rstrip().endswith('event: done\ndata: {"status": "completed"}')

    resumed = c.get(f"{URL}/{RUN}/events", headers={"Last-Event-ID": "2"}).text
    assert [l for l in resumed.splitlines() if l.startswith("event:")] == ["event: run.completed", "event: done"]
    assert c.get(f"{URL}/{RUN}/events?after=3").text.count("event:") == 1  # only done
    assert calls["after"][0] == 0 and 2 in calls["after"] and 3 in calls["after"]
