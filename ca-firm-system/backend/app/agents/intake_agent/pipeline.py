# ruff: noqa: E501
"""Pure pipeline: parsed grids -> structured table drafts. No database, no network except the
optional assistant. Deterministic given the same input (the assistant only fills in suggestions)."""

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from app.agents.intake_agent.classify import (
    ColumnProfile,
    category_type,
    guess_role,
    normalize_header,
    profile_column,
    scan_preamble,
    score_document_type,
)
from app.agents.intake_agent.layout import Layout, detect_layout, synthetic_header
from app.agents.intake_agent.llm import MAX_LLM_CONFIDENCE, ColumnQuery, IntakeAssistant
from app.agents.intake_agent.normalize import NormalizedTable, normalize_rows
from app.agents.intake_agent.types import (
    PARSER_VERSION,
    ROLES,
    FindingDraft,
    ParsedFile,
    RawCell,
    SourceGrid,
    col_letter,
)
from app.agents.intake_agent.values import is_blank

logger = logging.getLogger("app.intake")
REVIEW_BELOW = 0.7  # columns/types under this confidence require a human decision
__all__ = ["PARSER_VERSION", "TableDraft", "build_tables"]


@dataclass
class ColumnDraft:
    col_index: int
    letter: str
    header_raw: str | None
    header_normalized: str
    header_synthetic: bool
    role: str
    confidence: float
    source: str  # header | content | combined | none | llm | carried
    confirmed_role: str | None = None  # carried over from a previous run


@dataclass
class TableDraft:
    name: str
    kind: str
    source_ref: dict[str, Any]
    columns: list[ColumnDraft]
    raw_rows: list[list[RawCell | None]]  # data rows only, padded to len(columns)
    row_numbers: list[int]
    row_refs: list[dict[str, Any]]
    normalized: NormalizedTable
    detected_type: str
    type_confidence: float
    type_source: str
    currency: str | None
    period_start: date | None
    period_end: date | None
    header_row: int | None
    has_header: bool
    status: str
    metadata: dict[str, Any] = field(default_factory=dict)
    findings: list[FindingDraft] = field(default_factory=list)
    llm_used: bool = False
    llm_model: str | None = None


def _pad(row: list[RawCell | None], n: int) -> list[RawCell | None]:
    return (row + [None] * n)[:n]


async def build_tables(
    parsed: ParsedFile,
    *,
    category: str | None,
    default_date_order: str,
    assistant: IntakeAssistant | None,
    llm_min_confidence: float = REVIEW_BELOW,
    carried_roles: dict[tuple[str, str], str] | None = None,
) -> list[TableDraft]:
    tables: list[TableDraft] = []
    carried = carried_roles or {}
    for grid in parsed.grids:
        t = await _build_one(
            grid, category, default_date_order, assistant, llm_min_confidence, carried
        )
        if t is not None:
            tables.append(t)
    return tables


def _preamble_lines(grid: SourceGrid, lay: Layout) -> list[str]:
    lines: list[str] = []
    for i in lay.preamble_rows:
        cells = [c.v.strip() for c in grid.rows[i] if c is not None and not is_blank(c)]
        if cells:
            lines.append(" ".join(cells))
    return lines


async def _build_one(
    grid: SourceGrid,
    category: str | None,
    order: str,
    assistant: IntakeAssistant | None,
    min_conf: float,
    carried: dict[tuple[str, str], str],
) -> TableDraft | None:
    if grid.kind in ("pdf_text", "ocr_text"):
        return _text_table(grid)
    lay = detect_layout(grid)
    if not lay.data_rows or lay.ncols == 0:
        return None
    findings = list(grid.findings)
    if lay.extra_blocks:
        findings.append(
            FindingDraft(
                "extra_blocks_ignored", "info",
                f"{len(lay.extra_blocks)} additional block(s) of cells below or beside the main table "
                "were not imported; they remain in the original file.",
                details={"blocks": [[grid.row_numbers[a], grid.row_numbers[b]] for a, b in lay.extra_blocks]},
            )
        )  # fmt: skip
    if not lay.has_header:
        findings.append(
            FindingDraft(
                "no_header_row", "warning",
                "No header row was found; columns are named by letter. Please assign column roles.",
            )
        )  # fmt: skip
    if lay.blank_rows_skipped:
        findings.append(
            FindingDraft(
                "blank_rows_skipped", "info", f"{lay.blank_rows_skipped} blank row(s) inside the table were skipped."
            )
        )  # fmt: skip

    headers = [h if h else synthetic_header(i) for i, h in enumerate(lay.headers)]
    data = [_pad(grid.rows[i], lay.ncols) for i in lay.data_rows]
    nums = [grid.row_numbers[i] for i in lay.data_rows]
    refs = [
        {**(grid.row_refs[i] if i < len(grid.row_refs) else {}), "sheet": grid.name, "row": grid.row_numbers[i]}
        for i in lay.data_rows
    ]  # fmt: skip

    profiles: list[ColumnProfile] = [
        profile_column(c, lay.headers[c], [r[c] for r in data]) for c in range(lay.ncols)
    ]
    cols: list[ColumnDraft] = []
    for c, p in enumerate(profiles):
        g = guess_role(p)
        hnorm = normalize_header(lay.headers[c])
        cols.append(
            ColumnDraft(
                c,
                col_letter(c),
                lay.headers[c],
                hnorm,
                lay.header_synthetic[c],
                g.role,
                g.confidence,
                g.source,
            )
        )

    # carry over confirmed roles from the previous run (a re-run must not lose human decisions)
    for col in cols:
        prev = carried.get((grid.name, col.header_normalized)) if col.header_normalized else None
        if prev:
            col.confirmed_role = prev

    # document type from roles (confirmed roles take precedence)
    effective = {
        c.confirmed_role or c.role for c in cols if (c.confirmed_role or c.confidence >= min_conf)
    }
    cat_type = category_type(category)
    dtype, dconf = score_document_type(effective, cat_type)
    dsource = "heuristic"

    llm_used, llm_model = False, None
    weak = [
        c for c in cols if not c.confirmed_role and c.confidence < min_conf and c.role != "ignore"
    ]
    if assistant is not None and (weak or dtype == "unknown"):
        queries = [
            ColumnQuery(c.col_index, c.header_raw, profiles[c.col_index].sample)
            for c in (weak or cols)
        ]
        res = await assistant.suggest(queries, category, dtype if dtype != "unknown" else None)
        if res is not None:
            llm_used, llm_model = True, res.model
            by_idx = {c.col_index: c for c in cols}
            for ans in res.columns:
                target = by_idx.get(ans.index)
                conf = max(
                    0.0, min(ans.confidence, MAX_LLM_CONFIDENCE)
                )  # never trust a caller's cap
                if (
                    target is not None
                    and ans.role in ROLES
                    and not target.confirmed_role
                    and conf > target.confidence
                ):
                    target.role, target.confidence, target.source = ans.role, conf, "llm"
            if dtype == "unknown" and res.document_type and res.document_type != "unknown":
                dtype, dconf, dsource = res.document_type, 0.6, "llm"  # always below threshold

    roles = [c.confirmed_role or c.role for c in cols]
    pre = scan_preamble(_preamble_lines(grid, lay), order)
    normed = normalize_rows(data, list(range(len(data))), roles, list(headers), order)
    for nf in normed.findings:
        nf.origin = "normalize"
    findings.extend(normed.findings)

    if pre.ambiguous_currency and not pre.currency:
        findings.append(
            FindingDraft(
                "ambiguous_currency", "warning",
                "A currency symbol ($ or Rs) was found that is shared by several currencies; the currency was not guessed.",
            )
        )  # fmt: skip
    if cat_type and dtype != "unknown" and dtype != cat_type and dconf >= min_conf:
        findings.append(
            FindingDraft(
                "type_mismatch", "warning",
                f"File was uploaded as '{cat_type}' but its columns look like '{dtype}'.",
                details={"uploaded_as": cat_type, "detected": dtype},
            )
        )  # fmt: skip
    if dtype == "unknown":
        findings.append(
            FindingDraft("unknown_document_type", "warning", "The document type could not be determined; please set it.")
        )  # fmt: skip
    for col in cols:
        if not col.confirmed_role and col.confidence < min_conf and col.role != "ignore":
            findings.append(
                FindingDraft(
                    "low_confidence_column", "warning",
                    f"Column '{col.header_raw or col.letter}' is probably '{col.role}' "
                    f"({round(col.confidence * 100)}% sure). Please confirm.",
                    col_index=col.col_index, details={"suggested_role": col.role, "source": col.source},
                )
            )  # fmt: skip

    for col in cols:
        if col.source == "llm" and not col.confirmed_role:
            findings.append(
                FindingDraft(
                    "llm_suggested_role", "warning",
                    f"Column '{col.header_raw or col.letter}' was classified as '{col.role}' by the AI "
                    "assistant. Please confirm.",
                    col_index=col.col_index, details={"suggested_role": col.role},
                )
            )  # fmt: skip
    if dsource == "llm":
        findings.append(
            FindingDraft(
                "llm_suggested_type", "warning",
                f"The document type '{dtype}' was suggested by the AI assistant. Please confirm.",
                details={"suggested_type": dtype},
            )
        )  # fmt: skip

    needs_review = (
        dtype == "unknown"
        or dsource == "llm"
        or any(
            not c.confirmed_role
            and c.role != "ignore"
            and (c.confidence < min_conf or c.source == "llm")
            for c in cols
        )
    )
    return TableDraft(
        name=grid.name, kind=grid.kind,
        source_ref={"sheet": grid.name, **({"page": grid.meta["page"]} if "page" in grid.meta else {})},
        columns=cols, raw_rows=data, row_numbers=nums, row_refs=refs, normalized=normed,
        detected_type=dtype, type_confidence=dconf, type_source=dsource,
        currency=pre.currency, period_start=pre.period_start, period_end=pre.period_end,
        header_row=grid.row_numbers[lay.header_rows[0]] if lay.header_rows else None,
        has_header=lay.has_header, status="needs_review" if needs_review else "ok",
        metadata={"title": pre.title, "preamble": _preamble_lines(grid, lay)[:10], **{
            k: v for k, v in grid.meta.items() if k in ("encoding", "delimiter")}},
        findings=findings, llm_used=llm_used, llm_model=llm_model,
    )  # fmt: skip


def _text_table(grid: SourceGrid) -> TableDraft:
    """Prose-only documents (scanned letters, notes) are kept as text lines, one row per page."""
    rows: list[list[RawCell | None]] = [[r[0]] if r else [None] for r in grid.rows]
    col = ColumnDraft(0, "A", "Text", "text", False, "description", 1.0, "content")
    return TableDraft(
        name=grid.name, kind=grid.kind, source_ref={"sheet": grid.name}, columns=[col],
        raw_rows=rows, row_numbers=grid.row_numbers, row_refs=[{"page": n} for n in grid.row_numbers],
        normalized=normalize_rows(rows, list(range(len(rows))), ["description"], ["Text"]),
        detected_type="text_document", type_confidence=0.9, type_source="heuristic",
        currency=None, period_start=None, period_end=None, header_row=None, has_header=False,
        status="needs_review",
        findings=[
            *grid.findings,
            FindingDraft("no_table_found", "warning",
                         "No tabular data was found; the page text was kept for review."),
        ],
    )  # fmt: skip
