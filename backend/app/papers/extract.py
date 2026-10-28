"""PDF bytes -> section- and page-tagged text chunks. Pure (no DB, no network) so it is unit-tested directly.

Per page: PyMuPDF text blocks -> drop running headers/footers/page numbers -> reading order (one or two
columns; a block spanning the middle breaks the column groups) -> clean -> heading detection. Body text under
"References" is skipped until an appendix heading. Paragraphs are then packed into ~CHUNK_CHARS chunks that
never cross a section, overlapping by OVERLAP_CHARS inside a section.
"""

import re
import statistics
from dataclasses import dataclass

import pymupdf

PIPELINE_VERSION = 1  # bump when extraction or chunking changes: every ready paper is re-processed
MAX_PDF_BYTES = 40 * 1024 * 1024
MAX_PAGES = 300
CHUNK_CHARS = 1800
OVERLAP_CHARS = 200
MARGIN = 0.06  # top/bottom fraction of the page where running headers and footers live

_KNOWN_HEADINGS = {
    "abstract", "introduction", "background", "related work", "related works", "preliminaries",
    "method", "methods", "methodology", "approach", "model", "experiments", "experimental setup",
    "evaluation", "results", "analysis", "discussion", "limitations", "conclusion", "conclusions",
    "future work", "acknowledgments", "acknowledgements",
}
_REFERENCES = {"references", "bibliography", "works cited", "literature cited"}
_NUMBERING = re.compile(r"^(?:\d+(?:\.\d+)*\.?|[IVX]+\.|[A-Z]\.?(?:\d+(?:\.\d+)*)?)\s+")
_NUMBERED = re.compile(r"^(?:\d+(?:\.\d+)*\.?|[IVX]+\.)\s+[A-Z]")
_APPENDIX = re.compile(r"^(?i:appendix|supplementary)|^[A-Z](?:\.\d+)*\.?\s+[A-Z]")


class PermanentError(Exception):
    """The file can never yield text (not a PDF, encrypted, too big, scanned). Retrying won't help."""


@dataclass(frozen=True)
class Chunk:
    section: str | None
    page_start: int
    page_end: int
    text: str


def _clean(text: str) -> str:
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\ufffd]", "", text)  # Postgres rejects NUL; U+FFFD = unmapped glyph
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)  # dehyphenate line breaks
    return re.sub(r"\s+", " ", text).strip()


def _blocks(page) -> list[dict]:
    """Text blocks in reading order, without running headers/footers, each with its text and font facts."""
    width, height = page.rect.width, page.rect.height
    out = []
    for b in page.get_text("dict")["blocks"]:
        if b["type"] != 0:
            continue
        spans = [s for line in b["lines"] for s in line["spans"] if s["text"].strip()]
        if not spans:
            continue
        text = _clean("\n".join("".join(s["text"] for s in line["spans"]) for line in b["lines"]))
        x0, y0, x1, y1 = b["bbox"]
        in_margin = y1 < height * MARGIN or y0 > height * (1 - MARGIN)
        if not text or text.isdigit() or (in_margin and len(text) < 100):
            continue
        out.append({
            "text": text, "x0": x0, "y0": y0, "x1": x1, "lines": len(b["lines"]),
            "size": max(s["size"] for s in spans),
            "bold": all(s["flags"] & 16 or "bold" in s["font"].lower() for s in spans),
        })

    # Two columns: a block wholly left or right of the middle belongs to that column; one that crosses
    # the middle is full-width and ends the current group (left column first, then right).
    mid, ordered, left, right = width / 2, [], [], []
    for b in sorted(out, key=lambda b: (b["y0"], b["x0"])):
        if b["x1"] <= mid + 5:
            left.append(b)
        elif b["x0"] >= mid - 5:
            right.append(b)
        else:
            ordered += left + right + [b]
            left, right = [], []
    return ordered + left + right


def _heading(block: dict, body_size: float) -> str | None:
    text = block["text"]
    if block["lines"] > 2 or len(text) > 80:
        return None
    name = _NUMBERING.sub("", text).rstrip(".:").strip().lower()
    if name in _KNOWN_HEADINGS or name in _REFERENCES:
        return text
    emphasised = block["bold"] or block["size"] > body_size * 1.15
    if emphasised and (_NUMBERED.match(text) or _APPENDIX.match(text)) and not text.endswith("."):
        return text
    return None


def _split_long(text: str) -> list[str]:
    limit = CHUNK_CHARS - OVERLAP_CHARS - 1  # room for the overlap carried in front of each piece
    pieces = []
    while len(text) > limit:
        cut = text.rfind(" ", 0, limit)
        cut = cut if cut > limit // 2 else limit
        pieces.append(text[:cut].strip())
        text = text[cut:].strip()
    return pieces + ([text] if text else [])


def _pack(paragraphs: list[tuple[str | None, int, str]]) -> list[Chunk]:
    chunks: list[Chunk] = []
    section, start, end, buf = None, 0, 0, ""

    def flush():
        if buf:
            chunks.append(Chunk(section, start, end, buf))

    for sec, page, para in paragraphs:
        for piece in _split_long(para):
            if buf and sec != section:
                flush()
                buf = ""
            if buf and len(buf) + 1 + len(piece) > CHUNK_CHARS:
                flush()
                tail = buf[-OVERLAP_CHARS:]
                buf, start = tail[tail.find(" ") + 1:] if " " in tail else tail, end
            if not buf:
                start = page
            section, end = sec, page
            buf = f"{buf} {piece}".strip()
    flush()
    return chunks


def extract_chunks(data: bytes) -> tuple[int, list[Chunk]]:
    """Returns (page_count, chunks). Raises PermanentError for anything that will never parse."""
    if b"%PDF" not in data[:1024]:  # MuPDF "repairs" almost anything into an empty document
        raise PermanentError("not a PDF")
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise PermanentError(f"not a readable PDF ({type(exc).__name__})") from exc
    with doc:
        if doc.needs_pass:
            raise PermanentError("the PDF is password-protected")
        if doc.page_count > MAX_PAGES:
            raise PermanentError(f"the PDF has {doc.page_count} pages (limit {MAX_PAGES})")
        pages = [(page.number + 1, _blocks(page)) for page in doc]
        page_count = doc.page_count

    sizes = [b["size"] for _, blocks in pages for b in blocks]
    body_size = statistics.median(sizes) if sizes else 10.0  # body paragraphs outnumber headings

    paragraphs, section, skipping = [], None, False
    for page_no, blocks in pages:
        for b in blocks:
            heading = _heading(b, body_size)
            if heading:
                name = _NUMBERING.sub("", heading).rstrip(".:").strip().lower()
                if name in _REFERENCES:
                    skipping = True
                    continue
                if skipping and _APPENDIX.match(heading):
                    skipping = False
                if not skipping:
                    section = heading
                continue
            if not skipping:
                paragraphs.append((section, page_no, b["text"]))

    if not paragraphs:
        raise PermanentError("no extractable text (scanned PDF? OCR is not supported)")
    return page_count, _pack(paragraphs)
