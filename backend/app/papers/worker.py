"""Background PDF ingestion: claim a job from ingestion_jobs, fetch the PDF, extract, swap the chunks in.

Runs as a task inside the API process (main.lifespan). Claims use FOR UPDATE SKIP LOCKED, so any number of
processes can run this loop against one database without taking the same job twice.
"""

import asyncio
import hashlib
import logging

import httpx
from sqlalchemy import text

from app import database  # looked up per call, so tests can swap database.AsyncSessionLocal
from app.papers.extract import MAX_PDF_BYTES, PermanentError, extract_chunks

log = logging.getLogger(__name__)

MAX_ATTEMPTS = 3
STALE_SECONDS = 600  # a job "running" this long belongs to a process that died
RETRY_SECONDS = 5

# Tests swap this for an httpx.MockTransport.
transport: httpx.AsyncBaseTransport | None = None


async def download(url: str) -> bytes:
    async with httpx.AsyncClient(
        timeout=30, follow_redirects=True, transport=transport, headers={"User-Agent": "Tangent/1.0 (research)"}
    ) as client:
        async with client.stream("GET", url) as r:
            if r.status_code in (401, 403, 404, 410):
                raise PermanentError(f"the PDF link returned HTTP {r.status_code}")
            r.raise_for_status()  # anything else (5xx, 429) is worth retrying
            data = bytearray()
            async for part in r.aiter_bytes():
                data += part
                if len(data) > MAX_PDF_BYTES:
                    raise PermanentError("the PDF is larger than 40 MB")
    if b"%PDF" not in data[:1024]:
        raise PermanentError("the link did not return a PDF")
    return bytes(data)


async def claim() -> dict | None:
    async with database.AsyncSessionLocal() as db:
        await db.execute(text(f"""
            UPDATE ingestion_jobs SET status = 'pending'
            WHERE status = 'running' AND locked_at < now() - interval '{STALE_SECONDS} seconds'
        """))
        job = (await db.execute(text("""
            UPDATE ingestion_jobs SET status = 'running', attempts = attempts + 1, locked_at = now()
            WHERE id = (
                SELECT id FROM ingestion_jobs WHERE status = 'pending' AND run_after <= now()
                ORDER BY run_after LIMIT 1 FOR UPDATE SKIP LOCKED
            )
            RETURNING id, paper_id, pipeline_version, attempts
        """))).mappings().first()
        if job:
            await db.execute(
                text("UPDATE papers SET status = 'processing', updated_at = now() WHERE id = :p AND status <> 'ready'"),
                {"p": job["paper_id"]},
            )
        await db.commit()
        return dict(job) if job else None


async def run_job(job: dict) -> None:
    async with database.AsyncSessionLocal() as db:
        paper = (await db.execute(
            text("SELECT pdf_url, pdf_sha256 FROM papers WHERE id = :p"), {"p": job["paper_id"]}
        )).mappings().one()
        data = None
        if paper["pdf_sha256"]:
            data = (await db.execute(
                text("SELECT bytes FROM paper_files WHERE sha256 = :s"), {"s": paper["pdf_sha256"]}
            )).scalar()
        if data is not None:
            log.info("papers pdf cache hit p%s sha=%s", job["paper_id"], paper["pdf_sha256"][:12])
        else:
            if not paper["pdf_url"]:
                raise PermanentError("no PDF is available for this paper")
            log.info("papers pdf cache miss p%s; downloading %s", job["paper_id"], paper["pdf_url"])
            data = await download(paper["pdf_url"])
            # keep the bytes before extracting, so a retry or a later pipeline version never re-downloads
            sha = hashlib.sha256(data).hexdigest()
            await db.execute(
                text("INSERT INTO paper_files (sha256, bytes) VALUES (:s, :b) ON CONFLICT DO NOTHING"),
                {"s": sha, "b": data},
            )
            await db.execute(text("UPDATE papers SET pdf_sha256 = :s WHERE id = :p"), {"s": sha, "p": job["paper_id"]})
            await db.commit()

    page_count, chunks = await asyncio.to_thread(extract_chunks, bytes(data))

    async with database.AsyncSessionLocal() as db:  # one transaction: readers see the old chunks or the new, never a mix
        await db.execute(text("DELETE FROM paper_chunks WHERE paper_id = :p"), {"p": job["paper_id"]})
        await db.execute(
            text("""INSERT INTO paper_chunks (paper_id, idx, section, page_start, page_end, text)
                    VALUES (:p, :i, :section, :page_start, :page_end, :text)"""),
            [{"p": job["paper_id"], "i": i, "section": c.section, "page_start": c.page_start,
              "page_end": c.page_end, "text": c.text} for i, c in enumerate(chunks)],
        )
        await db.execute(text("""
            UPDATE papers SET status = 'ready', page_count = :n, pipeline_version = :v, error = NULL, updated_at = now()
            WHERE id = :p
        """), {"p": job["paper_id"], "n": page_count, "v": job["pipeline_version"]})
        await db.execute(text("UPDATE ingestion_jobs SET status = 'done', error = NULL WHERE id = :j"), {"j": job["id"]})
        await db.commit()
    log.info("papers ingested p%s: %d pages, %d chunks", job["paper_id"], page_count, len(chunks))


async def _fail(job: dict, exc: Exception) -> None:
    permanent = isinstance(exc, PermanentError)
    final = permanent or job["attempts"] >= MAX_ATTEMPTS
    message = (str(exc) if permanent else f"{type(exc).__name__}: {exc}")[:500]
    paper_status = "unavailable" if permanent else "failed" if final else "queued"
    async with database.AsyncSessionLocal() as db:
        await db.execute(text("""
            UPDATE ingestion_jobs SET status = :s, error = :e, run_after = now() + make_interval(secs => :delay)
            WHERE id = :j
        """), {"s": "failed" if final else "pending", "e": message, "delay": RETRY_SECONDS * job["attempts"], "j": job["id"]})
        # a ready paper (re-processing for a new pipeline version) keeps serving its old chunks
        await db.execute(
            text("UPDATE papers SET status = :s, error = :e, updated_at = now() WHERE id = :p AND status <> 'ready'"),
            {"s": paper_status, "e": message, "p": job["paper_id"]},
        )
        await db.commit()
    log.warning("papers ingest p%s attempt %d failed (%s): %s", job["paper_id"], job["attempts"], paper_status, message)


async def run_once() -> bool:
    """Process one job if there is one. Returns whether there was."""
    job = await claim()
    if job is None:
        return False
    try:
        await run_job(job)
    except Exception as exc:
        await _fail(job, exc)
    return True


async def run_forever() -> None:
    delay = 1.0
    while True:
        try:
            worked = await run_once()
            delay = 1.0
        except Exception as exc:  # database down, tables missing: back off, never crash the app
            log.warning("paper worker: %s; retrying in %.0fs", type(exc).__name__, delay)
            worked, delay = False, min(delay * 2, 60)
        if not worked:
            await asyncio.sleep(delay)
