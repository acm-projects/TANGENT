import httpx

from debate.search_s2 import SemanticScholarSearch, _evidence
from helpers import run

PAPER = {"paperId": "abcdef1234567890", "title": " Solar cells ", "year": 2023, "url": "https://s2/p", "abstract": "long abstract",
         "tldr": {"text": "short take"}, "citationCount": 12}


def client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def make(handler, **kw):
    slept = []

    async def sleep(x):
        slept.append(x)

    return SemanticScholarSearch("KEY", client=client(handler), sleep=sleep, **kw), slept


def test_clips_long_abstracts_at_a_word_boundary_and_falls_back_to_the_tldr():
    long = {**PAPER, "abstract": "word " * 400}
    s = _evidence(long).snippet
    assert len(s) < 1100 and " … " in s + " " and "wor …" not in s and "cited 12" in s
    assert _evidence({**PAPER, "abstract": None}).snippet.startswith("short take")


def test_maps_papers_sends_the_key_and_prefers_the_abstract():
    seen = {}

    def handler(req):
        seen["key"], seen["q"] = req.headers.get("x-api-key"), req.url.params
        return httpx.Response(200, json={"total": 2, "data": [PAPER, {"paperId": None, "title": "x"}]})

    s, _ = make(handler)
    res = run(s.search("solar"))
    assert seen["key"] == "KEY" and seen["q"]["query"] == "solar" and "tldr" in seen["q"]["fields"]
    assert len(res) == 1 and res[0].id == "s2-abcdef123456" and res[0].title == "Solar cells" and res[0].year == 2023
    assert res[0].snippet.startswith("long abstract") and "cited 12" in res[0].snippet


def test_429_is_retried_then_succeeds():
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(429) if len(calls) < 3 else httpx.Response(200, json={"data": [PAPER]})

    s, slept = make(handler)
    assert len(run(s.search("q"))) == 1 and len(calls) == 3 and 1 in slept and 2 in slept


def test_persistent_failure_raises_so_the_graph_can_degrade():
    s, _ = make(lambda r: httpx.Response(429), retries=1)
    try:
        run(s.search("q"))
        assert False
    except httpx.HTTPStatusError:
        pass


def test_requests_are_spaced_by_the_shared_throttle():
    s, slept = make(lambda r: httpx.Response(200, json={"data": []}))
    run(s.search("a"))
    run(s.search("b"))
    assert any(0 < x <= 1.1 for x in slept)


def test_missing_title_or_id_is_dropped():
    assert _evidence({"paperId": "x"}) is None and _evidence({"title": "t"}) is None
