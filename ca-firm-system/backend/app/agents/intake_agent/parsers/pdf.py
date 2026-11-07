"""PDF parsing: native tables and text via PyMuPDF; scanned pages go through OCR."""

from app.agents.intake_agent.parsers.ocr import OcrEngine
from app.agents.intake_agent.types import (
    ExtractionError,
    FindingDraft,
    ParsedFile,
    RawCell,
    SourceGrid,
)
from app.agents.intake_agent.values import normalize_text

MIN_TEXT_CHARS = 20  # fewer characters on a page => treated as scanned


def _open(data: bytes):  # type: ignore[no-untyped-def]
    import pymupdf

    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception as exc:  # noqa: BLE001
        raise ExtractionError("corrupt_file", "PDF could not be read") from exc
    if doc.needs_pass or doc.is_encrypted:
        doc.close()
        raise ExtractionError("encrypted_file", "PDF is password protected")
    return doc


def _word_rows(page) -> list[list[str]]:  # type: ignore[no-untyped-def]
    """Group words into lines by y, then split each line into cells at wide horizontal gaps."""
    words = page.get_text("words")  # x0,y0,x1,y1,text,block,line,wordno
    if not words:
        return []
    heights = sorted(w[3] - w[1] for w in words)
    h = heights[len(heights) // 2] or 10.0
    lines: list[tuple[float, list[tuple[float, float, str]]]] = []
    for w in sorted(words, key=lambda w: ((w[1] + w[3]) / 2, w[0])):
        mid = (w[1] + w[3]) / 2
        if lines and abs(lines[-1][0] - mid) <= 0.5 * h:
            lines[-1][1].append((w[0], w[2], w[4]))
        else:
            lines.append((mid, [(w[0], w[2], w[4])]))
    rows: list[list[str]] = []
    for _, line_toks in lines:
        toks = sorted(line_toks)
        cells, cur = [], [toks[0]]
        for t in toks[1:]:
            if t[0] - cur[-1][1] > 1.2 * h:  # a wide gap starts a new cell
                cells.append(cur)
                cur = [t]
            else:
                cur.append(t)
        cells.append(cur)
        rows.append([" ".join(x[2] for x in c) for c in cells])
    return rows


def _page_grids(doc, ocr: bool, max_rows: int) -> list[SourceGrid]:  # type: ignore[no-untyped-def]
    grids: list[SourceGrid] = []
    kind = "ocr_table" if ocr else "pdf_table"
    for pno, page in enumerate(doc, start=1):
        rows: list[list[RawCell | None]] = []
        if not ocr and page.get_drawings():  # ruled tables: PyMuPDF's line-based detector
            try:
                tables = page.find_tables().tables
            except Exception:  # noqa: BLE001
                tables = []
            for tb in tables:
                part = [
                    [RawCell(normalize_text(c)) if c and c.strip() else None for c in r]
                    for r in tb.extract()
                ]
                if sum(1 for r in part for c in r if c) >= 4:
                    rows.extend(part)
        if not rows:
            split = _word_rows(page)
            multi = [r for r in split if len(r) >= 2]
            if len(multi) >= 3 and len(multi) >= 0.5 * len(split):
                rows = [[RawCell(normalize_text(c)) for c in r] for r in split]
        if rows:
            rows = rows[:max_rows]
            grids.append(
                SourceGrid(
                    name=f"Page {pno}", kind=kind, rows=rows,
                    row_numbers=list(range(1, len(rows) + 1)),
                    row_refs=[{"page": pno}] * len(rows), meta={"page": pno},
                )
            )  # fmt: skip
    return grids


def parse_pdf(
    data: bytes, *, max_pages: int, max_rows: int, ocr_engine: OcrEngine | None
) -> ParsedFile:
    doc = _open(data)
    try:
        if doc.page_count > max_pages:
            raise ExtractionError("too_many_pages", f"PDF has more than {max_pages} pages")
        if doc.page_count == 0:
            raise ExtractionError("empty_file", "PDF has no pages")
        scanned = [len(p.get_text("text").strip()) < MIN_TEXT_CHARS for p in doc]
        out = ParsedFile(grids=[])
        work, ocr_used = data, False
        if all(scanned) or any(scanned):
            if ocr_engine is None:
                out.findings.append(
                    FindingDraft(
                        "ocr_unavailable", "error",
                        "Scanned pages were found but OCR is disabled or unavailable.",
                    )
                )  # fmt: skip
            else:
                work = ocr_engine.ocr_pdf(data)
                ocr_used = True
        d2 = _open(work) if ocr_used else doc
        try:
            out.grids = _page_grids(d2, ocr_used, max_rows)
            texts = [normalize_text(p.get_text("text")) for p in d2]
        finally:
            if d2 is not doc:
                d2.close()
        out.ocr_applied = ocr_used
        if ocr_used:
            out.findings.append(
                FindingDraft(
                    "ocr_applied", "warning",
                    "Text was recognised by OCR; values may contain recognition errors. "
                    "Review against the original.",
                )
            )  # fmt: skip
        if not out.grids:
            joined = "\n".join(t for t in texts if t)
            if not joined:
                raise ExtractionError("no_content", "No readable text or tables were found")
            out.grids.append(
                SourceGrid(
                    name="Text", kind="ocr_text" if ocr_used else "pdf_text",
                    rows=[[RawCell(t)] for t in texts if t],
                    row_numbers=[i + 1 for i, t in enumerate(texts) if t],
                )
            )  # fmt: skip
        return out
    finally:
        doc.close()
