"""Paper registry, ingestion queue and worker against the real DB. Semantic Scholar and PDF hosts are faked.
Skipped without DATABASE_URL + JWT_SECRET_KEY (CI has no database). Deletes its papers afterwards."""
import asyncio
import os
import sys
import uuid

import httpx
import pytest
from dotenv import load_dotenv

load_dotenv()
if not (os.getenv("DATABASE_URL") and os.getenv("JWT_SECRET_KEY")):
    pytest.skip("needs DATABASE_URL and JWT_SECRET_KEY (a real database)", allow_module_level=True)

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app import database
from app.database import DATABASE_URL, _local
from app.papers import s2, service, worker

sys.path.insert(0, os.path.dirname(__file__))
from test_extract import _pdf  # noqa: E402

TAG = f"tangent-test-{uuid.uuid4().hex[:8]}"
PDF = _pdf()


def _engine():
    return create_async_engine(DATABASE_URL, poolclass=NullPool,
                               connect_args={"statement_cache_size": 0, **({} if _local else {"ssl": "require"})})


@pytest.fixture(autouse=True)
def db(monkeypatch):
    """Unpooled sessions (each asyncio.run is a new loop), the schema in place, and cleanup afterwards."""
    engine = _engine()
    sessions = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False, autoflush=False)
    monkeypatch.setattr(database, "AsyncSessionLocal", sessions)  # app.papers looks it up per call

    async def schema():
        async with engine.begin() as c:
            for statement in database._ADDED_COLUMNS:
                await c.execute(text(statement))

    asyncio.run(schema())
    yield sessions

    async def cleanup():
        async with engine.begin() as c:
            shas = (await c.execute(text("SELECT pdf_sha256 FROM papers WHERE source_id LIKE :t"), {"t": TAG + "%"})).scalars().all()
            await c.execute(text("DELETE FROM papers WHERE source_id LIKE :t"), {"t": TAG + "%"})
            await c.execute(text("""DELETE FROM paper_files f WHERE f.sha256 = ANY(:s)
                                    AND NOT EXISTS (SELECT 1 FROM papers p WHERE p.pdf_sha256 = f.sha256)"""),
                            {"s": [s for s in shas if s]})
        await engine.dispose()

    asyncio.run(cleanup())


@pytest.fixture
def pdf_host(monkeypatch):
    """Serves PDF at /ok.pdf, 503 at /flaky.pdf, 404 at /gone.pdf. Counts requests per path."""
    hits = {}

    def handler(request: httpx.Request) -> httpx.Response:
        hits[request.url.path] = hits.get(request.url.path, 0) + 1
        if request.url.path == "/ok.pdf":
            return httpx.Response(200, content=PDF)
        return httpx.Response(503 if request.url.path == "/flaky.pdf" else 404)

    monkeypatch.setattr(worker, "transport", httpx.MockTransport(handler))
    return hits


async def _paper(sessions, name: str, url: str | None):
    async with sessions() as db:
        row = await service._upsert_s2(db, {
            "source_id": f"{TAG}-{name}", "title": f"{TAG} {name}", "authors": ["Ada"], "year": 2024,
            "abstract": "An abstract.", "doi": None, "arxiv_id": None, "pdf_url": url,
        })
        await db.commit()
        return row


async def _row(sessions, paper_id: int):
    async with sessions() as db:
        return (await db.execute(text("SELECT * FROM papers WHERE id = :i"), {"i": paper_id})).mappings().one()


async def _jobs(sessions, paper_id: int):
    async with sessions() as db:
        return (await db.execute(text("SELECT * FROM ingestion_jobs WHERE paper_id = :i ORDER BY id"),
                                 {"i": paper_id})).mappings().all()


async def _drain(paper_id_of_interest: int, sessions) -> None:
    """Run the worker until our paper's job is no longer pending-and-due (other jobs may be in the queue)."""
    for _ in range(50):
        jobs = await _jobs(sessions, paper_id_of_interest)
        if not any(j["status"] in ("pending", "running") for j in jobs):
            return
        async with sessions() as db:  # skip the retry backoff
            await db.execute(text("UPDATE ingestion_jobs SET run_after = now() WHERE paper_id = :i"), {"i": paper_id_of_interest})
            await db.commit()
        if not await worker.run_once():
            await asyncio.sleep(0.2)


def test_ingest_once_then_serve_evidence_and_reuse_bytes(db, pdf_host, monkeypatch):
    async def run():
        paper = await _paper(db, "ok", "https://pdfs.test/ok.pdf")

        await asyncio.gather(*(service.ensure_ingest(paper) for _ in range(5)))  # concurrent requests
        assert len(await _jobs(db, paper["id"])) == 1
        assert (await _row(db, paper["id"]))["status"] == "queued"

        await _drain(paper["id"], db)
        row = await _row(db, paper["id"])
        assert row["status"] == "ready" and row["page_count"] == 3 and row["pdf_sha256"]
        assert pdf_host == {"/ok.pdf": 1}

        result = await service.search_paper_evidence(f"p{paper['id']}", "right column method", wait_seconds=0)
        top = result["evidence"][0]
        assert top["evidence_id"].startswith(f"p{paper['id']}:c") and top["section"] == "2 Method"
        assert top["pages"] == "1"
        assert await service.verify_quote(top["evidence_id"], "right COLUMN words  about the method")
        assert not await service.verify_quote(top["evidence_id"], "words the paper never says")
        assert "must not be indexed" not in str(result)

        # a second request is served from the cache: no new job, no download
        await service.ensure_ingest(await _row(db, paper["id"]))
        assert len(await _jobs(db, paper["id"])) == 1 and pdf_host == {"/ok.pdf": 1}

        # a new pipeline version re-processes from the stored bytes; the old chunks serve meanwhile
        monkeypatch.setattr(service, "PIPELINE_VERSION", 2)
        await service.ensure_ingest(await _row(db, paper["id"]))
        assert (await _row(db, paper["id"]))["status"] == "ready"
        await _drain(paper["id"], db)
        assert (await _row(db, paper["id"]))["pipeline_version"] == 2
        assert pdf_host == {"/ok.pdf": 1}

    asyncio.run(run())


def test_failures_retry_then_give_up(db, pdf_host):
    async def run():
        flaky = await _paper(db, "flaky", "https://pdfs.test/flaky.pdf")
        gone = await _paper(db, "gone", "https://pdfs.test/gone.pdf")
        none = await _paper(db, "nopdf", None)
        for p in (flaky, gone, none):
            await service.ensure_ingest(p)
        assert await _jobs(db, none["id"]) == []  # nothing to fetch, nothing queued

        await _drain(flaky["id"], db)
        await _drain(gone["id"], db)
        f_job, = await _jobs(db, flaky["id"])
        assert f_job["status"] == "failed" and f_job["attempts"] == worker.MAX_ATTEMPTS and "503" in f_job["error"]
        assert (await _row(db, flaky["id"]))["status"] == "failed"
        g_job, = await _jobs(db, gone["id"])
        assert g_job["attempts"] == 1 and (await _row(db, gone["id"]))["status"] == "unavailable"

        result = await service.search_paper_evidence(f"p{gone['id']}", "anything", wait_seconds=0)
        assert result["full_text"] == "unavailable" and result["abstract"] == "An abstract."
        assert "404" in result["message"]

    asyncio.run(run())


def test_search_uses_registry_before_semantic_scholar(db, monkeypatch):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(200, json={"data": [{
            "paperId": f"{TAG}-s2", "title": f"Zyzzogeton {TAG} retrieval", "authors": [{"name": "Ada"}],
            "year": 2023, "abstract": "About retrieval.", "externalIds": {}, "openAccessPdf": {"url": "https://x.test/a.pdf"},
        }]})

    monkeypatch.setattr(s2, "transport", httpx.MockTransport(handler))

    async def run():
        first = await service.search_papers(f"zyzzogeton {TAG}", limit=1)
        assert len(calls) == 1 and first["results"][0]["full_text"] == "on_demand"
        second = await service.search_papers(f"zyzzogeton {TAG}", limit=1)
        assert len(calls) == 1  # served from the registry
        assert second["results"] == first["results"]

    asyncio.run(run())
