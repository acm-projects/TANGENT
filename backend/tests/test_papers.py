"""The research tools' pure helpers: budgets, citations, quote checks, S2 normalization (runs in CI, no DB)."""
import os

_dummies = {"DATABASE_URL": "postgresql://dummy@localhost/dummy", "JWT_SECRET_KEY": "test-secret"}
_added = [k for k in _dummies if k not in os.environ]
os.environ.update({k: _dummies[k] for k in _added})

from app.papers import s2
from app.papers.service import citations_in, fill_budget, full_text_state, parse_leaked_tool_calls, prefer_accessible, quote_matches

for _k in _added:
    del os.environ[_k]


def test_fill_budget_keeps_rank_order_and_cuts_the_last():
    rows = [{"text": "a " * 200}, {"text": "b " * 200}, {"text": "c " * 200}]  # ~100 tokens each
    kept, truncated = fill_budget(rows, 260)
    assert [body[0] for _, body in kept] == ["a", "b", "c"]
    assert truncated and len(kept[2][1]) < len(rows[2]["text"])
    assert fill_budget(rows[:1], 4000) == ([(rows[0], rows[0]["text"])], False)


def test_fill_budget_never_returns_nothing_for_one_huge_chunk():
    kept, truncated = fill_budget([{"text": "word " * 5000}], 100)
    assert truncated and len(kept) == 1 and len(kept[0][1]) <= 100 * 4 + 2


def test_quote_matches_ignores_case_and_whitespace():
    chunk = "We evaluate on   MS MARCO\nand report MRR@10."
    assert quote_matches(chunk, "evaluate on ms marco and report")
    assert not quote_matches(chunk, "evaluate on TREC")
    assert not quote_matches(chunk, "   ")


def test_citations_in_dedupes_in_order():
    assert citations_in("A [p1:c2]. B [p3:c0] and again [p1:c2]; not p4:c1.") == ["p1:c2", "p3:c0"]


def test_full_text_state():
    row = lambda status, url=None, sha=None: {"status": status, "pdf_url": url, "pdf_sha256": sha}
    assert full_text_state(row("ready")) == "ready"
    assert full_text_state(row("queued")) == full_text_state(row("processing")) == "processing"
    assert full_text_state(row("metadata_only", url="u")) == "on_demand"
    assert full_text_state(row("metadata_only")) == "unavailable"  # no PDF anywhere
    assert full_text_state(row("failed", url="u")) == full_text_state(row("unavailable", url="u")) == "unavailable"


def test_s2_normalize_falls_back_to_arxiv_pdf():
    meta = s2.normalize({"paperId": "abc", "title": "T", "authors": [{"name": "Ada"}], "year": 2020,
                         "externalIds": {"ArXiv": "2001.00001", "DOI": "10.1/x"}, "openAccessPdf": None})
    assert meta["pdf_url"] == "https://arxiv.org/pdf/2001.00001"
    assert meta["authors"] == ["Ada"] and meta["doi"] == "10.1/x"


def test_prefer_accessible_reorders_slightly_but_keeps_a_far_more_relevant_abstract():
    paper = lambda name, url=None: {"name": name, "status": "metadata_only", "pdf_url": url, "pdf_sha256": None}
    abstract_first = paper("abstract-1")
    ranked = [abstract_first, paper("abstract-2"), paper("open-3", "u"), paper("open-4", "u")]
    # an open paper two places down overtakes the first abstract-only one, within the bonus
    assert [r["name"] for r in prefer_accessible(ranked, 3)] == ["open-3", "abstract-1", "open-4"]
    far = [paper(f"abstract-{i}") for i in range(6)] + [paper("open-late", "u")]
    assert prefer_accessible(far, 2)[0]["name"] == "abstract-0"  # far more relevant: not displaced
    assert [r["name"] for r in prefer_accessible([paper("a"), paper("b")], 5)] == ["a", "b"]  # only abstracts: still returned


def test_parse_leaked_tool_calls():
    calls = parse_leaked_tool_calls("<tool_call> <function=search_papers> <parameter=query> a b </parameter> "
                                    "<parameter=limit> 10 </parameter> </function> </tool_call>")
    assert [(c["function"]["name"], c["function"]["arguments"]) for c in calls] == [
        ("search_papers", '{"query": "a b", "limit": 10}')]
    assert parse_leaked_tool_calls("<tool_call>no function here") == []
