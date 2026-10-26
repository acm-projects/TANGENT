"""extract_chunks against a PDF built in the test: two columns, headings, a page number, references, an appendix."""
import pymupdf
import pytest

from app.papers.extract import CHUNK_CHARS, PermanentError, _clean, extract_chunks

LEFT = "Left column words about tree search. " * 6
RIGHT = "Right column words about the method. " * 6
LONG = "Results sentence with numbers twelve. " * 120  # > one chunk, so it splits with overlap


def _text(page, rect, text, size=10, bold=False):
    assert page.insert_textbox(pymupdf.Rect(*rect), text, fontsize=size, fontname="hebo" if bold else "helv") >= 0


def _pdf() -> bytes:
    doc = pymupdf.open()
    p1 = doc.new_page()  # 595 x 842
    _text(p1, (60, 50, 535, 90), "A Paper Title Spanning The Page", size=16, bold=True)
    _text(p1, (60, 95, 280, 122), "1 Introduction", size=12, bold=True)
    _text(p1, (60, 125, 280, 400), LEFT)
    _text(p1, (315, 95, 535, 122), "2 Method", size=12, bold=True)
    _text(p1, (315, 125, 535, 400), RIGHT)
    _text(p1, (290, 812, 310, 832), "1")  # page number in the footer
    p2 = doc.new_page()
    _text(p2, (60, 55, 535, 82), "3 Results", size=12, bold=True)
    _text(p2, (60, 85, 535, 790), LONG)
    p3 = doc.new_page()
    _text(p3, (60, 55, 535, 82), "References", size=12, bold=True)
    _text(p3, (60, 85, 535, 200), "Smith, J. A cited paper that must not be indexed. 2020.")
    _text(p3, (60, 205, 535, 232), "A Proofs", size=12, bold=True)
    _text(p3, (60, 235, 535, 400), "Appendix text that should be indexed.")
    return doc.tobytes()


def test_sections_order_pages_and_references():
    pages, chunks = extract_chunks(_pdf())
    assert pages == 3
    by_section = {}
    for c in chunks:
        by_section.setdefault(c.section, []).append(c)

    assert "Left column" in by_section["1 Introduction"][0].text
    assert "Right column" in by_section["2 Method"][0].text
    assert chunks.index(by_section["1 Introduction"][0]) < chunks.index(by_section["2 Method"][0])

    results = by_section["3 Results"]
    assert len(results) >= 2 and all(c.page_start == c.page_end == 2 for c in results)
    assert all(len(c.text) <= CHUNK_CHARS for c in results)
    assert results[1].text[:40] in results[0].text  # overlap carried into the next chunk

    everything = " ".join(c.text for c in chunks)
    assert "must not be indexed" not in everything
    assert by_section["A Proofs"][0].text == "Appendix text that should be indexed."
    assert by_section["A Proofs"][0].page_start == 3
    assert not any(c.text.strip() == "1" for c in chunks)


def test_not_a_pdf():
    with pytest.raises(PermanentError):
        extract_chunks(b"<html>not a pdf</html>")


def test_no_text():
    doc = pymupdf.open()
    doc.new_page()
    with pytest.raises(PermanentError):
        extract_chunks(doc.tobytes())


def test_clean_strips_nul_and_dehyphenates():
    assert _clean("Lewis\x00\ufffd, retrie-\nval   aug") == "Lewis, retrieval aug"
