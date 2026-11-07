"""CSV parsing with encoding and delimiter detection."""

import csv
import io

from app.agents.intake_agent.types import (
    ExtractionError,
    FindingDraft,
    ParsedFile,
    RawCell,
    SourceGrid,
)

_ENCODINGS = ("utf-8-sig", "utf-16", "cp1252")


def decode(data: bytes) -> tuple[str, str]:
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16"), "utf-16"
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(enc), enc
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1"), "latin-1"


def parse_csv(data: bytes, max_rows: int) -> ParsedFile:
    if b"\x00" in data[:4096] and not data.startswith((b"\xff\xfe", b"\xfe\xff")):
        raise ExtractionError("corrupt_file", "File does not look like text CSV")
    text, enc = decode(data)
    sample = text[:20000]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        delim = dialect.delimiter
    except csv.Error:
        delim = ","
    rows: list[list[RawCell | None]] = []
    nums: list[int] = []
    truncated = False
    try:
        for i, rec in enumerate(csv.reader(io.StringIO(text, newline=""), delimiter=delim), 1):
            if len(rows) >= max_rows:
                truncated = True
                break
            rows.append([RawCell(c) if c.strip() != "" else None for c in rec])
            nums.append(i)
    except csv.Error as exc:
        raise ExtractionError("corrupt_file", f"CSV could not be parsed: {exc}") from exc
    if not any(c for r in rows for c in r):
        raise ExtractionError("empty_file", "The CSV contains no data")
    grid = SourceGrid(name="CSV", kind="csv", rows=rows, row_numbers=nums,
                      meta={"encoding": enc, "delimiter": delim})  # fmt: skip
    if truncated:
        grid.findings.append(
            FindingDraft("rows_truncated", "warning", f"Only the first {max_rows} rows were read.")
        )
    return ParsedFile(grids=[grid])
