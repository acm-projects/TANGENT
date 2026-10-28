"""web_search with Bright Data faked (runs in CI, no secrets)."""
import asyncio
import json
import os

import httpx
import pytest

_dummies = {"DATABASE_URL": "postgresql://dummy@localhost/dummy", "JWT_SECRET_KEY": "test-secret"}
_added = [k for k in _dummies if k not in os.environ]
os.environ.update({k: _dummies[k] for k in _added})

from app import web_search
from app.agent import tools
from app.papers import service as paper_service
from app.routers import nodes_router

for _k in _added:
    del os.environ[_k]

SERP = {
    "organic": [
        {"link": "https://a.test/1", "title": "One", "description": "x" * 900, "rank": 1},
        {"link": "javascript:alert(1)", "title": "Bad scheme"},
        {"link": "https://a.test/1", "title": "Duplicate"},
        {"title": "No link"},
    ],
    "news": [{"link": "https://n.test/2", "title": "Two", "description": "d", "source": "N Times", "date": "1 hour ago"}],
}


@pytest.fixture
def bd(monkeypatch):
    monkeypatch.setenv("BRIGHTDATA_API_KEY", "key")
    monkeypatch.setenv("BRIGHTDATA_SERP_ZONE", "serp1")
    seen, reply = [], {"status": 200, "json": SERP}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.headers["authorization"], json.loads(request.content)))
        return httpx.Response(reply["status"], json=reply["json"])

    monkeypatch.setattr(web_search, "transport", httpx.MockTransport(handler))
    return seen, reply


def run(**args):
    return asyncio.run(web_search.web_search(**args))


def test_both_nodes_and_the_agent_have_it():
    assert "web_search" in [t["function"]["name"] for t in paper_service.TOOLS]
    assert "web_search" in [t["function"]["name"] for t in tools.AGENT_TOOLS]
    assert nodes_router.paper_service.TOOLS is paper_service.TOOLS


def test_results_are_cleaned_and_the_request_is_a_google_search(bd):
    seen, _ = bd
    out = run(query="  ai news ", limit=5, recency="week")
    assert [r["url"] for r in out["results"]] == ["https://a.test/1", "https://n.test/2"]  # bad scheme, dupe, no link dropped
    assert len(out["results"][0]["snippet"]) == web_search.SNIPPET_CHARS
    assert out["results"][1]["source"] == "N Times" and out["results"][1]["date"] == "1 hour ago"
    auth, body = seen[0]
    assert auth == "Bearer key" and body["zone"] == "serp1" and body["format"] == "raw"
    assert "gl=us" in body["url"] and "q=ai+news" in body["url"] and "tbs=qdr%3Aw" in body["url"] and "brd_json=1" in body["url"] and "tbm" not in body["url"]


def test_news_mode_searches_news_and_lists_news_first(bd):
    seen, _ = bd
    out = run(query="x", news=True, limit=1)
    assert [r["url"] for r in out["results"]] == ["https://n.test/2"] and "tbm=nws" in seen[0][1]["url"]


def test_failures_come_back_as_errors(bd, monkeypatch):
    _, reply = bd
    assert "error" in run(query=" ")
    reply.update(status=403, json={"error": "no"})
    assert "HTTP 403" in run(query="x")["error"]
    reply.update(status=200, json=["not", "a", "dict"])
    assert "unreadable" in run(query="x")["error"]
    reply.update(status=200, json={"organic": []})
    assert run(query="x") == {"query": "x", "results": [], "message": "No results; try different keywords."}
    monkeypatch.delenv("BRIGHTDATA_SERP_ZONE")
    assert "not configured" in run(query="x")["error"]


def test_dispatchers_route_web_search(bd):
    assert asyncio.run(paper_service.call_tool("web_search", {"query": "x"}))["results"]
