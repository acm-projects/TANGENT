"""A project's uploaded PDFs (the Sources panel). Each upload becomes a paper the research tools can search."""

import hashlib
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db_session
from app.models import User
from app.papers.extract import MAX_PDF_BYTES
from app.papers.service import ensure_ingest, full_text_state
from app.routers.projects_router import get_project_with_role, require_owner

router = APIRouter(prefix="/projects", tags=["Sources"], dependencies=[Depends(get_current_user)])


class SourceOut(BaseModel):
    """Mirrors `Source` in frontend/src/api/types.ts."""

    id: str  # the paper id the research tools use, e.g. "p12"
    name: str
    kind: str = "pdf"
    thumbnail_url: Optional[str] = None
    use_count: int = 0  # shortcut: always 0 until messages record which sources they cite
    status: str  # ready | processing | on_demand | unavailable


def _out(row) -> SourceOut:
    return SourceOut(id=f"p{row['id']}", name=row["title"], status=full_text_state(row))


@router.get("/{project_id}/sources", response_model=list[SourceOut])
async def list_sources(
    project_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db_session)
):
    await get_project_with_role(db, project_id, user)
    rows = await db.execute(
        text("SELECT * FROM papers WHERE source = 'upload' AND project_id = :p ORDER BY created_at, id"),
        {"p": project_id},
    )
    return [_out(r) for r in rows.mappings()]


@router.post("/{project_id}/sources", response_model=SourceOut, status_code=201)
async def upload_source(
    project_id: UUID,
    file: UploadFile,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Owner only: a shared project is view-only. Re-uploading the same file returns the existing source."""
    await require_owner(db, project_id, user)
    data = await file.read(MAX_PDF_BYTES + 1)
    if len(data) > MAX_PDF_BYTES:
        raise HTTPException(413, "The PDF must be 40 MB or smaller.")
    if b"%PDF" not in data[:1024]:
        raise HTTPException(415, "Only PDF files are supported.")
    sha = hashlib.sha256(data).hexdigest()
    name = (file.filename or "Untitled.pdf").strip()[:200] or "Untitled.pdf"

    await db.execute(
        text("INSERT INTO paper_files (sha256, bytes) VALUES (:s, :b) ON CONFLICT DO NOTHING"), {"s": sha, "b": data}
    )
    row = (await db.execute(text("""
        INSERT INTO papers (source, source_id, project_id, title, pdf_sha256)
        VALUES ('upload', :sid, :p, :title, :s)
        ON CONFLICT (source, source_id) DO UPDATE SET updated_at = now()
        RETURNING *
    """), {"sid": f"{project_id}:{sha}", "p": project_id, "title": name, "s": sha})).mappings().one()
    await db.commit()

    await ensure_ingest(row)
    row = (await db.execute(text("SELECT * FROM papers WHERE id = :id"), {"id": row["id"]})).mappings().one()
    return _out(row)
