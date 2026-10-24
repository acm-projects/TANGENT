"""Research tools over the paper registry: the one entry point (call_tool) for chat and, later, Debate Mode.

Papers are shown to the model as "p{id}", evidence passages as "p{id}:c{chunk idx}". Tool results are
bounded (see the caps below) and never contain a paper's full text. Every result is chunk text from the
PDF itself, never chat content, so one agent's conclusions can't come back to another as source evidence.
"""

import asyncio
import json
import logging
import re
from uuid import UUID

from sqlalchemy import text

from app import database  # looked up per call, so tests can swap database.AsyncSessionLocal
from app.papers import s2
from app.papers.extract import PIPELINE_VERSION

log = logging.getLogger(__name__)

MAX_SEARCH = 10
MAX_EVIDENCE = 10
MAX_EVIDENCE_TOKENS = 4000
MAX_WAIT_SECONDS = 25
ABSTRACT_PREVIEW = 300

RESEARCH_SYSTEM_PROMPT = (
    "You can look up research papers with the tools search_papers, get_paper and search_paper_evidence. "
    "When a claim depends on a paper, use search_paper_evidence to read the relevant passages and cite each "
    "one inline by its evidence id in square brackets, e.g. [p12:c7]. Cite only evidence ids a tool returned "
    "in this conversation; never invent a paper, id, page or quote. If a paper's full text is unavailable or "
    "still processing, say so and rely only on its abstract, labelled as such. If the evidence is missing, "
    "thin or conflicting, say that plainly instead of guessing."
)

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_papers",
            "description": "Find research papers by keywords. Returns paper ids, metadata, a short abstract and "
                           "whether the full text can be searched (full_text: ready | processing | on_demand | "
                           "unavailable). Includes papers the user uploaded to this project.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Keywords, e.g. 'retrieval augmented generation'"},
                    "limit": {"type": "integer", "description": f"Max results, 1-{MAX_SEARCH} (default 5)"},
                    "year_from": {"type": "integer", "description": "Only papers from this year on"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_paper",
            "description": "Metadata and full abstract for one paper, and start fetching its full text. "
                           "paper: an id from search_papers (e.g. 'p12'), a Semantic Scholar id, "
                           "'DOI:10.xxx/yyy' or 'ARXIV:2101.00001'.",
            "parameters": {
                "type": "object",
                "properties": {"paper": {"type": "string"}},
                "required": ["paper"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_paper_evidence",
            "description": "Search inside one paper's full text and return the best-matching passages, each "
                           "with an evidence_id to cite, its section and pages. Waits briefly if the paper is "
                           "still being processed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "paper_id": {"type": "string", "description": "e.g. 'p12'"},
                    "query": {"type": "string", "description": "What to look for, as keywords"},
                    "max_results": {"type": "integer", "description": f"1-{MAX_EVIDENCE} (default 5)"},
                    "max_tokens": {"type": "integer", "description": f"Budget for all passages, up to {MAX_EVIDENCE_TOKENS} (default 2000)"},
                },
                "required": ["paper_id", "query"],
            },
        },
    },
]

_PAPER_REF = re.compile(r"p(\d+)")
EVIDENCE_ID = re.compile(r"p(\d+):c(\d+)")
_CITATION = re.compile(r"\[(p\d+:c\d+)\]")


def _clamp(value, default: int, lo: int, hi: int) -> int:
    try:
        return max(lo, min(hi, int(value)))
    except (TypeError, ValueError):
        return default


def full_text_state(row) -> str:
    status = row["status"]
    if status == "ready":
        return "ready"
    if status in ("queued", "processing"):
        return "processing"
    if status == "metadata_only" and (row["pdf_url"] or row["pdf_sha256"]):
        return "on_demand"
    return "unavailable"


def _summary(row) -> dict:
    abstract = row["abstract"] or ""
    authors = row["authors"]
    authors = json.loads(authors) if isinstance(authors, str) else authors or []  # asyncpg hands jsonb back as text
    return {
        "paper_id": f"p{row['id']}",
        "title": row["title"],
        "authors": authors[:5],
        "year": row["year"],
        "abstract": abstract[:ABSTRACT_PREVIEW] + ("…" if len(abstract) > ABSTRACT_PREVIEW else ""),
        "full_text": full_text_state(row),
        **({"uploaded": True} if row["source"] == "upload" else {}),
    }


def _pages(start: int, end: int) -> str:
    return str(start) if start == end else f"{start}-{end}"


def fill_budget(rows, max_tokens: int) -> tuple[list[tuple[dict, str]], bool]:
    """Keep rows in rank order until ~max_tokens (4 chars/token); the last one may be cut. Returns (kept, truncated)."""
    kept, used = [], 0
    for row in rows:
        cost = len(row["text"]) // 4 + 1
        if used + cost <= max_tokens:
            kept.append((row, row["text"]))
            used += cost
            continue
        room = max_tokens - used
        if room > 50 or not kept:
            kept.append((row, row["text"][: room * 4].rsplit(" ", 1)[0] + " …"))
        return kept, True
    return kept, False


def quote_matches(chunk_text: str, quote: str) -> bool:
    norm = lambda s: " ".join(s.split()).lower()
    return bool(quote.strip()) and norm(quote) in norm(chunk_text)


def sources_note(rows) -> str:
    """Names a project's uploads for the system prompt. search_papers matches only titles and abstracts, and an
    upload has no abstract, so without this the model can't know an upload exists to search its evidence."""
    if not rows:
        return ""
    listed = "\n".join(f"- p{r['id']}: {r['title']} (full_text: {full_text_state(r)})" for r in rows)
    return (
        "\n\nThe user uploaded these sources to this project:\n" + listed + "\n"
        "When a question could be answered from them, call search_paper_evidence on the relevant ones first, "
        "before answering or asking the user to clarify."
    )


async def project_sources_note(project_id: UUID) -> str:
    """sources_note for this project's uploads (at most 20). Best effort: a failed lookup only leaves it out."""
    try:
        async with database.AsyncSessionLocal() as db:
            rows = (await db.execute(text("""
                SELECT id, title, status, pdf_url, pdf_sha256 FROM papers
                WHERE source = 'upload' AND project_id = :p ORDER BY created_at, id LIMIT 20
            """), {"p": project_id})).mappings().all()
    except Exception:
        log.exception("listing uploads for project %s failed", project_id)
        return ""
    return sources_note(rows)


def citations_in(answer: str) -> list[str]:
    return list(dict.fromkeys(_CITATION.findall(answer)))


# --- registry -------------------------------------------------------------------------------------------

_UPSERT_S2 = text("""
    INSERT INTO papers (source, source_id, title, authors, year, abstract, doi, arxiv_id, pdf_url)
    VALUES ('s2', :source_id, :title, CAST(:authors AS jsonb), :year, :abstract, :doi, :arxiv_id, :pdf_url)
    ON CONFLICT (source, source_id) DO UPDATE SET
        title = EXCLUDED.title, authors = EXCLUDED.authors, year = EXCLUDED.year,
        abstract = coalesce(EXCLUDED.abstract, papers.abstract), doi = coalesce(EXCLUDED.doi, papers.doi),
        arxiv_id = coalesce(EXCLUDED.arxiv_id, papers.arxiv_id),
        pdf_url = coalesce(EXCLUDED.pdf_url, papers.pdf_url), updated_at = now()
    RETURNING *
""")


async def _upsert_s2(db, meta: dict):
    return (await db.execute(_UPSERT_S2, {**meta, "authors": json.dumps(meta["authors"])})).mappings().one()


async def _load(db, paper_id: int, project_id: UUID | None):
    """A paper this project may see: any S2 paper, or an upload to this project."""
    return (await db.execute(
        text("SELECT * FROM papers WHERE id = :id AND (project_id IS NULL OR project_id = CAST(:pid AS uuid))"),
        {"id": paper_id, "pid": str(project_id) if project_id else None},
    )).mappings().first()


async def resolve(ref: str, project_id: UUID | None):
    """'p12' -> registry row. Any other ref is an S2 id: registry first, then S2 (and upsert). None if unknown."""
    ref = (ref or "").strip()
    async with database.AsyncSessionLocal() as db:
        if m := _PAPER_REF.fullmatch(ref):
            return await _load(db, int(m.group(1)), project_id)
        kind, _, value = ref.partition(":")
        if kind.upper() == "DOI" and value:
            where, v = "lower(doi) = :v", value.lower()
        elif kind.upper() == "ARXIV" and value:
            where, v = "arxiv_id = :v", value
        else:
            where, v = "source_id = :v", ref
        row = (await db.execute(text(f"SELECT * FROM papers WHERE source = 's2' AND {where}"), {"v": v})).mappings().first()
        if row:
            log.info("papers registry hit ref=%s -> p%s", ref, row["id"])
            return row
        log.info("papers registry miss ref=%s; asking Semantic Scholar", ref)
        meta = await s2.get(ref)
        if meta is None:
            return None
        row = await _upsert_s2(db, meta)
        await db.commit()
        return row


async def add_to_project(row, project_id: UUID | None) -> None:
    """A Semantic Scholar paper the agent read in a project joins that project's Sources panel.
    Best effort: failing to list it must not fail the tool call."""
    if project_id is None or row["source"] != "s2":
        return
    try:
        async with database.AsyncSessionLocal() as db:
            await db.execute(text("""
                INSERT INTO project_papers (project_id, paper_id) VALUES (:p, :id) ON CONFLICT DO NOTHING
            """), {"p": project_id, "id": row["id"]})
            await db.commit()
    except Exception:
        log.exception("adding p%s to project %s's sources failed", row["id"], project_id)


def paper_url(row) -> str | None:
    """Where to read a Semantic Scholar paper: its open PDF, else its DOI, else its S2 page. Uploads have none."""
    if row["source"] != "s2":
        return None
    if (row["pdf_url"] or "").startswith(("https://", "http://")):  # it is rendered as a link: no javascript: URLs
        return row["pdf_url"]
    if row["doi"]:
        return f"https://doi.org/{row['doi']}"
    return f"https://www.semanticscholar.org/paper/{row['source_id']}"


async def ensure_ingest(row) -> None:
    """Queue full-text ingestion unless it is impossible, already queued/running/given up, or current.
    The (paper_id, pipeline_version) unique key makes concurrent callers create one job between them."""
    if not (row["pdf_url"] or row["pdf_sha256"]):
        return
    status = row["status"]
    if status in ("queued", "processing", "unavailable"):
        return
    if status == "ready" and row["pipeline_version"] == PIPELINE_VERSION:
        return
    params = {"id": row["id"], "v": PIPELINE_VERSION}
    async with database.AsyncSessionLocal() as db:
        if status == "failed":
            # retries ran out on transient errors; give it another go once an hour has passed
            again = (await db.execute(text("""
                UPDATE ingestion_jobs SET status = 'pending', attempts = 0, run_after = now()
                WHERE paper_id = :id AND pipeline_version = :v AND status = 'failed'
                  AND locked_at < now() - interval '1 hour'
                RETURNING id
            """), params)).first()
            if again:
                await db.execute(text("UPDATE papers SET status = 'queued', updated_at = now() WHERE id = :id"), params)
                await db.commit()
                return
        inserted = (await db.execute(text("""
            INSERT INTO ingestion_jobs (paper_id, pipeline_version) VALUES (:id, :v)
            ON CONFLICT (paper_id, pipeline_version) DO NOTHING RETURNING id
        """), params)).first()
        if inserted:
            # a ready paper keeps serving its old chunks until the new version swaps them in
            await db.execute(
                text("UPDATE papers SET status = 'queued', updated_at = now() WHERE id = :id AND status <> 'ready'"),
                params,
            )
        await db.commit()
    log.info("papers ingest p%s: %s", row["id"], "job enqueued" if inserted else "job already exists")


# --- tools ----------------------------------------------------------------------------------------------

async def search_papers(query: str, limit=5, year_from=None, *, project_id: UUID | None = None) -> dict:
    query = (query or "").strip()
    if not query:
        return {"error": "query is empty"}
    limit = _clamp(limit, 5, 1, MAX_SEARCH)
    year = _clamp(year_from, 0, 0, 3000) or None
    async with database.AsyncSessionLocal() as db:
        rows = list((await db.execute(text("""
            SELECT * FROM papers, plainto_tsquery('english', :q) AS q
            WHERE search_tsv @@ q
              AND (project_id IS NULL OR project_id = CAST(:pid AS uuid))
              AND (CAST(:year AS int) IS NULL OR year >= CAST(:year AS int))
            ORDER BY ts_rank_cd(search_tsv, q) DESC LIMIT :limit
        """), {"q": query, "pid": str(project_id) if project_id else None, "year": year, "limit": limit})).mappings())
        if len(rows) >= limit:
            log.info("papers search cache hit q=%r local=%d", query, len(rows))
            return {"results": [_summary(r) for r in rows]}
        log.info("papers search cache miss q=%r local=%d; asking Semantic Scholar", query, len(rows))
        try:
            found = await s2.search(query, limit, year)
        except s2.S2Error as exc:
            return {"results": [_summary(r) for r in rows], "warning": str(exc) + "; showing cached papers only"}
        seen = {r["id"] for r in rows}
        for meta in found:
            row = await _upsert_s2(db, meta)
            if row["id"] not in seen and len(rows) < limit:
                rows.append(row)
                seen.add(row["id"])
        await db.commit()
    return {"results": [_summary(r) for r in rows]}


async def get_paper(paper: str, *, project_id: UUID | None = None) -> dict:
    try:
        row = await resolve(paper, project_id)
    except s2.S2Error as exc:
        return {"error": str(exc)}
    if row is None:
        return {"error": f"No paper found for {paper!r}. Use search_papers to find one."}
    await add_to_project(row, project_id)
    await ensure_ingest(row)
    async with database.AsyncSessionLocal() as db:
        row = await _load(db, row["id"], project_id)
    return {
        **_summary(row),
        "abstract": row["abstract"],
        "doi": row["doi"],
        "arxiv_id": row["arxiv_id"],
        "page_count": row["page_count"],
    }


async def search_paper_evidence(
    paper_id: str, query: str, max_results=5, max_tokens=2000, wait_seconds=10, *, project_id: UUID | None = None
) -> dict:
    max_results = _clamp(max_results, 5, 1, MAX_EVIDENCE)
    max_tokens = _clamp(max_tokens, 2000, 100, MAX_EVIDENCE_TOKENS)
    wait = _clamp(wait_seconds, 10, 0, MAX_WAIT_SECONDS)
    try:
        row = await resolve(paper_id, project_id)
    except s2.S2Error as exc:
        return {"error": str(exc)}
    if row is None:
        return {"error": f"No paper found for {paper_id!r}. Use search_papers to find one."}
    await add_to_project(row, project_id)
    await ensure_ingest(row)

    loop = asyncio.get_running_loop()
    deadline = loop.time() + wait
    async with database.AsyncSessionLocal() as db:
        while row["status"] != "ready" and full_text_state(row) == "processing" and loop.time() < deadline:
            await asyncio.sleep(0.5)
            row = await _load(db, row["id"], project_id)
            await db.rollback()  # end the read so the next poll sees the worker's commit
        if row["status"] != "ready":
            state = full_text_state(row)
            return {
                "paper_id": f"p{row['id']}",
                "full_text": state,
                "abstract": row["abstract"],
                "message": "The full text is still being processed; try again shortly, or use the abstract."
                if state == "processing" else
                f"The full text is unavailable ({row['error'] or 'no open-access PDF'}); only the abstract can be used.",
            }
        hits = list((await db.execute(text("""
            SELECT idx, section, page_start, page_end, text
            FROM paper_chunks, CAST(replace(CAST(plainto_tsquery('english', :q) AS text), '&', '|') AS tsquery) AS q
            WHERE paper_id = :id AND tsv @@ q
            ORDER BY ts_rank_cd(tsv, q, 1) DESC, idx LIMIT :n
        """), {"q": query or "", "id": row["id"], "n": max_results})).mappings())

    kept, truncated = fill_budget(hits, max_tokens)
    return {
        "paper_id": f"p{row['id']}",
        "title": row["title"],
        "evidence": [
            {
                "evidence_id": f"p{row['id']}:c{h['idx']}",
                "section": h["section"],
                "pages": _pages(h["page_start"], h["page_end"]),
                "text": body,
            }
            for h, body in kept
        ],
        "truncated": truncated,
        **({} if hits else {"message": "No passage matched; try different keywords."}),
    }


_HANDLERS = {"search_papers": search_papers, "get_paper": get_paper, "search_paper_evidence": search_paper_evidence}


async def call_tool(name: str, args: dict, project_id: UUID | None = None) -> dict:
    """Run one tool. Never raises: failures come back as {"error": ...} so the conversation carries on."""
    handler = _HANDLERS.get(name)
    if handler is None:
        return {"error": f"Unknown tool {name!r}"}
    if not isinstance(args, dict):
        return {"error": "Tool arguments must be a JSON object"}
    try:
        return await handler(**args, project_id=project_id)
    except TypeError as exc:
        log.warning("bad arguments for %s: %s", name, exc)
        return {"error": f"Bad arguments for {name}: {exc}"}
    except Exception:
        log.exception("research tool %s failed", name)
        return {"error": "The research tool failed; continue without it and say so."}


async def verify_quote(evidence_id: str, quote: str) -> bool:
    """Does `quote` appear (whitespace- and case-insensitively) in the stored chunk it cites?"""
    m = EVIDENCE_ID.fullmatch(evidence_id or "")
    if not m:
        return False
    async with database.AsyncSessionLocal() as db:
        chunk = (await db.execute(
            text("SELECT text FROM paper_chunks WHERE paper_id = :p AND idx = :i"),
            {"p": int(m.group(1)), "i": int(m.group(2))},
        )).scalar()
    return chunk is not None and quote_matches(chunk, quote)
