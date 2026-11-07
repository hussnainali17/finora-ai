"""Excel parsing with cell coordinates preserved (openpyxl for .xlsx, xlrd for .xls)."""

import io
import zipfile
from decimal import Decimal
from typing import Any

from app.agents.intake_agent.types import (
    ExtractionError,
    FindingDraft,
    ParsedFile,
    RawCell,
    SourceGrid,
)
from app.agents.intake_agent.values import is_blank


def _num(v: Any) -> str:
    return format(Decimal(repr(v)) if isinstance(v, float) else Decimal(v), "f")


def parse_xlsx(data: bytes, max_rows: int, max_uncompressed: int) -> ParsedFile:
    import openpyxl
    from openpyxl.utils.exceptions import InvalidFileException

    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            if sum(i.file_size for i in z.infolist()) > max_uncompressed:
                raise ExtractionError(
                    "file_too_large", "Workbook expands beyond the safe size limit"
                )
    except zipfile.BadZipFile as exc:
        raise ExtractionError("corrupt_file", "File is not a valid .xlsx workbook") from exc
    try:
        wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True, read_only=False)
    except (InvalidFileException, KeyError, ValueError, OSError) as exc:
        raise ExtractionError("corrupt_file", f"Workbook could not be read: {exc}") from exc
    out = ParsedFile(grids=[])
    for ws in wb.worksheets:
        findings: list[FindingDraft] = []
        if ws.sheet_state != "visible":
            out.findings.append(
                FindingDraft("hidden_sheet", "info", f"Sheet '{ws.title}' is hidden; it was read.")
            )
        merges = [
            (m.min_row, m.max_row, m.min_col - 1, m.max_col - 1) for m in ws.merged_cells.ranges
        ]
        rows: list[list[RawCell | None]] = []
        nums: list[int] = []
        truncated = False
        for r_idx, row in enumerate(ws.iter_rows(), start=1):
            if len(rows) >= max_rows:
                truncated = True
                break
            cells: list[RawCell | None] = []
            for c in row:
                v = c.value
                if v is None:
                    cells.append(None)
                elif isinstance(v, bool):
                    cells.append(RawCell("TRUE" if v else "FALSE", "b"))
                elif isinstance(v, (int, float, Decimal)):
                    cells.append(RawCell(_num(v), "n"))
                elif hasattr(v, "isoformat"):
                    cells.append(RawCell(v.isoformat(), "d"))
                elif c.data_type == "e":
                    cells.append(RawCell(str(v), "e"))
                else:
                    cells.append(RawCell(str(v), "s"))
            rows.append(cells)
            nums.append(r_idx)
        if truncated:
            findings.append(
                FindingDraft(
                    "rows_truncated", "warning",
                    f"Sheet '{ws.title}' has more than {max_rows} rows; the rest was not read.",
                )
            )  # fmt: skip
        err = sum(1 for r in rows for c in r if c is not None and c.t == "e")
        if err:
            findings.append(
                FindingDraft(
                    "spreadsheet_errors", "warning", f"{err} cell(s) contain Excel errors."
                )
            )
        if any(not is_blank(c) for r in rows for c in r):
            out.grids.append(
                SourceGrid(
                    name=ws.title, kind="sheet", rows=rows, row_numbers=nums,
                    meta={"merges": merges}, findings=findings,
                )
            )  # fmt: skip
    wb.close()
    if not out.grids:
        raise ExtractionError("empty_file", "The workbook contains no data")
    return out


def parse_xls(data: bytes, max_rows: int) -> ParsedFile:
    import xlrd

    try:
        book = xlrd.open_workbook(file_contents=data, formatting_info=False)
    except (xlrd.XLRDError, ValueError, OSError) as exc:
        raise ExtractionError("corrupt_file", f"Workbook could not be read: {exc}") from exc
    out = ParsedFile(grids=[])
    for sh in book.sheets():
        rows: list[list[RawCell | None]] = []
        nums: list[int] = []
        for r in range(min(sh.nrows, max_rows)):
            cells: list[RawCell | None] = []
            for c in range(sh.ncols):
                t, v = sh.cell_type(r, c), sh.cell_value(r, c)
                if t in (xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK):
                    cells.append(None)
                elif t == xlrd.XL_CELL_NUMBER:
                    cells.append(RawCell(_num(v), "n"))
                elif t == xlrd.XL_CELL_DATE:
                    dt = xlrd.xldate.xldate_as_datetime(v, book.datemode)
                    cells.append(RawCell(dt.isoformat(), "d"))
                elif t == xlrd.XL_CELL_BOOLEAN:
                    cells.append(RawCell("TRUE" if v else "FALSE", "b"))
                elif t == xlrd.XL_CELL_ERROR:
                    cells.append(RawCell(str(v), "e"))
                else:
                    cells.append(RawCell(str(v), "s"))
            rows.append(cells)
            nums.append(r + 1)
        if any(not is_blank(c) for r in rows for c in r):
            g = SourceGrid(name=sh.name, kind="sheet", rows=rows, row_numbers=nums)
            if sh.nrows > max_rows:
                g.findings.append(
                    FindingDraft("rows_truncated", "warning", f"Sheet '{sh.name}' was truncated.")
                )
            out.grids.append(g)
    if not out.grids:
        raise ExtractionError("empty_file", "The workbook contains no data")
    return out
