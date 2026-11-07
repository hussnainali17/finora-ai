# ruff: noqa: E501
"""Derives normalized values from raw cells. Pure and deterministic; raw data is never touched.

Normalized value shape per row: {"<col index>": "<string>" | None}. Dates are ISO (YYYY-MM-DD),
amounts are fixed-point Decimal strings, text is NFC-normalized and trimmed. A value that cannot
be read is None and the row gets a flag; it is never replaced by zero or a guess."""

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from app.agents.intake_agent.types import (
    AMOUNT_ROLES,
    DATE_ROLES,
    TEXT_ROLES,
    FindingDraft,
    RawCell,
)
from app.agents.intake_agent.values import (
    amount_str,
    detect_decimal_style,
    excel_serial_to_date,
    is_blank,
    normalize_text,
    parse_amount,
    parse_date,
)

_TOTAL_ROW = re.compile(
    r"(?i)^\s*(grand\s+|sub\s*-?\s*)?(total|totals|net total|carried forward|brought forward|b/f|c/f)\b"
)


@dataclass
class NormalizedTable:
    rows: list[dict[str, str | None]] = field(default_factory=list)
    flags: list[list[dict[str, Any]]] = field(default_factory=list)
    findings: list[FindingDraft] = field(default_factory=list)


def _flag(code: str, col: int | None, message: str) -> dict[str, Any]:
    return {"code": code, "col": col, "message": message}


def normalize_rows(
    data: list[list[RawCell | None]],
    row_indexes: list[int],
    roles: list[str],
    headers: Sequence[str | None],
    default_date_order: str = "DMY",
) -> NormalizedTable:
    """`data[i]` is the raw row (padded/cropped to len(roles)); `row_indexes[i]` its table index."""
    ncols = len(roles)
    out = NormalizedTable(rows=[{} for _ in data], flags=[[] for _ in data])
    for c in range(ncols):
        col = [row[c] if c < len(row) else None for row in data]
        role, label = roles[c], headers[c] or f"column {c + 1}"
        if role in DATE_ROLES:
            _dates(out, col, c, label, row_indexes, default_date_order)
        elif role in AMOUNT_ROLES:
            _amounts(out, col, c, label, row_indexes)
        elif role == "ignore":
            continue
        else:
            for i, cell in enumerate(col):
                out.rows[i][str(c)] = (
                    normalize_text(cell.v) if cell and not is_blank(cell) else None
                )
    _flag_special_rows(out, data, roles)
    _flag_duplicates(out, data, row_indexes)
    return out


def _serial_date(cell: RawCell | None) -> date | None:
    if cell is None:
        return None
    try:
        return excel_serial_to_date(Decimal(cell.v))
    except ArithmeticError:
        return None


def _dates(
    out: NormalizedTable, col: list[RawCell | None], c: int, label: str, idx: list[int], order: str
) -> None:
    del idx
    first = [parse_date(x, order) for x in col]
    certain = {
        r.certain_order
        for x, r in zip(col, first, strict=True)
        if r.certain_order and not (x is not None and x.t == "n")
    }
    use = next(iter(certain)) if len(certain) == 1 else order
    if len(certain) > 1:
        out.findings.append(
            FindingDraft(
                "mixed_date_formats", "warning",
                f"'{label}' contains dates in both day-first and month-first order.",
                col_index=c,
            )
        )  # fmt: skip
    ambiguous_left = 0
    for i, cell in enumerate(col):
        shown = cell.v if cell else ""
        if cell is not None and cell.t == "n":  # Excel serial stored as a number
            d = _serial_date(cell)
            out.rows[i][str(c)] = d.isoformat() if d else None
            if d is None:
                out.flags[i].append(_flag("invalid_date", c, f"'{shown}' is not a valid date"))
            continue
        r = parse_date(cell, use)
        if r.status == "blank":
            out.rows[i][str(c)] = None
        elif r.status == "invalid":
            out.rows[i][str(c)] = None
            out.flags[i].append(_flag("invalid_date", c, f"'{shown}' is not a valid date"))
        else:
            out.rows[i][str(c)] = r.value.isoformat() if r.value else None
            if r.status == "ambiguous":
                ambiguous_left += 1
                out.flags[i].append(
                    _flag("ambiguous_date", c, f"'{shown}' could be day-first or month-first")
                )
    if ambiguous_left and not certain:
        out.findings.append(
            FindingDraft(
                "ambiguous_date_order", "warning",
                f"Dates in '{label}' could be day-first or month-first; {ambiguous_left} value(s) "
                f"were read as {use} because no date in the column settles it. Please confirm.",
                col_index=c, details={"assumed_order": use, "count": ambiguous_left},
            )
        )  # fmt: skip
    elif ambiguous_left:
        out.findings.append(
            FindingDraft(
                "date_order_inferred", "info",
                f"Dates in '{label}' were read as {use} because other dates in the column prove it.",
                col_index=c, details={"order": use},
            )
        )  # fmt: skip


def _amounts(
    out: NormalizedTable, col: list[RawCell | None], c: int, label: str, idx: list[int]
) -> None:
    style = detect_decimal_style([cell.v for cell in col if cell is not None and cell.t != "n"])
    if style == "comma":
        out.findings.append(
            FindingDraft(
                "european_number_format", "info",
                f"'{label}' uses 1.234,56 number format; read accordingly.", col_index=c,
            )
        )  # fmt: skip
    invalid = 0
    for i, cell in enumerate(col):
        r = parse_amount(cell, style)
        if r.status == "ok" and r.value is not None:
            out.rows[i][str(c)] = amount_str(r.value)
            if r.note:
                out.flags[i].append(_flag("sign_convention", c, r.note))
        else:
            out.rows[i][str(c)] = None
            if r.status == "invalid":
                invalid += 1
                out.flags[i].append(
                    _flag("invalid_amount", c, f"'{cell.v if cell else ''}' is not a valid amount")
                )
    if invalid:
        out.findings.append(
            FindingDraft(
                "invalid_amounts", "warning",
                f"{invalid} value(s) in '{label}' could not be read as amounts and were left empty.",
                col_index=c, details={"count": invalid},
            )
        )  # fmt: skip


def _flag_special_rows(
    out: NormalizedTable, data: list[list[RawCell | None]], roles: list[str]
) -> None:
    text_cols = [c for c, r in enumerate(roles) if r in TEXT_ROLES or r == "other"]
    amount_cols = [c for c, r in enumerate(roles) if r in AMOUNT_ROLES]
    for i, row in enumerate(data):
        for c in text_cols:
            cell = row[c] if c < len(row) else None
            if cell and _TOTAL_ROW.match(cell.v):
                out.flags[i].append(
                    _flag("total_row", c, "Looks like a total or carry-forward row")
                )
                break
        filled = sum(1 for c in range(len(roles)) if c < len(row) and not is_blank(row[c]))
        has_amount = any(out.rows[i].get(str(c)) for c in amount_cols)
        if filled and amount_cols and not has_amount and filled <= 2:
            out.flags[i].append(_flag("no_amounts", None, "Row has text but no amounts"))


def _flag_duplicates(
    out: NormalizedTable, data: list[list[RawCell | None]], idx: list[int]
) -> None:
    seen: dict[tuple[str, ...], int] = {}
    for i, row in enumerate(data):
        key = tuple((cell.v.strip() if cell else "") for cell in row)
        if not any(key):
            continue
        if key in seen:
            out.flags[i].append(
                _flag(
                    "duplicate_row",
                    None,
                    f"Identical to row {idx[seen[key]] + 1}; kept, not removed",
                )
            )
        else:
            seen[key] = i
