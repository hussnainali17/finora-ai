"""Finds the main table inside a grid: header row, data range, preamble and extra blocks."""

from dataclasses import dataclass, field

from app.agents.intake_agent.types import RawCell, SourceGrid, col_letter
from app.agents.intake_agent.values import is_blank, parse_amount, parse_date_text

HEADER_SEARCH_ROWS = 40
MIN_BLANK_GAP = 2  # this many blank rows separate two tables


@dataclass
class Layout:
    header_rows: list[int] = field(default_factory=list)  # grid row indexes
    data_rows: list[int] = field(default_factory=list)  # grid row indexes (non-blank, in order)
    preamble_rows: list[int] = field(default_factory=list)
    ncols: int = 0
    has_header: bool = True
    blank_rows_skipped: int = 0
    extra_blocks: list[tuple[int, int]] = field(default_factory=list)  # grid row ranges ignored
    headers: list[str | None] = field(default_factory=list)  # raw header text per column
    header_synthetic: list[bool] = field(default_factory=list)
    table_range: tuple[int, int] | None = None  # (first, last) grid row index of header+data


def cell_kind(cell: RawCell | None) -> str:
    """'blank' | 'num' | 'date' | 'text' - a cheap classification used for layout decisions only."""
    if is_blank(cell):
        return "blank"
    if cell is None:
        return "blank"
    if cell.t == "n":
        return "num"
    if cell.t == "d":
        return "date"
    if cell.t in ("b", "e"):
        return "text"
    text = cell.v.strip()
    if parse_amount(cell).status == "ok":
        return "num"
    if parse_date_text(text).status in ("ok", "ambiguous"):
        return "date"
    return "text"


def _row_stats(row: list[RawCell | None]) -> tuple[int, int, int]:
    kinds = [cell_kind(c) for c in row]
    return (
        sum(k != "blank" for k in kinds),
        sum(k in ("num", "date") for k in kinds),
        sum(k == "text" for k in kinds),
    )


def _blocks(nonblank: list[bool]) -> list[tuple[int, int]]:
    blocks: list[tuple[int, int]] = []
    start = None
    gap = 0
    last = -1
    for i, nb in enumerate(nonblank):
        if nb:
            if start is None:
                start = i
            last, gap = i, 0
        elif start is not None:
            gap += 1
            if gap >= MIN_BLANK_GAP:
                blocks.append((start, last))
                start, gap = None, 0
    if start is not None:
        blocks.append((start, last))
    return blocks


def _expand_h_merges(
    grid: SourceGrid, row_idx: int, row: list[RawCell | None]
) -> list[RawCell | None]:
    """Header text in a horizontally merged cell applies to every column it spans."""
    out = list(row)
    rn = grid.row_numbers[row_idx]
    for r0, r1, c0, c1 in grid.meta.get("merges", []):
        if r0 == r1 == rn and c1 > c0 and c0 < len(out) and out[c0] is not None:
            for c in range(c0 + 1, min(c1 + 1, len(out))):
                if is_blank(out[c]):
                    out[c] = out[c0]
    return out


def detect_layout(grid: SourceGrid) -> Layout:
    rows = grid.rows
    nonblank = [any(not is_blank(c) for c in r) for r in rows]
    lay = Layout()
    if not any(nonblank):
        return lay
    blocks = _blocks(nonblank)
    # main block = most populated cells
    sizes = [sum(sum(not is_blank(c) for c in rows[i]) for i in range(a, b + 1)) for a, b in blocks]
    main = blocks[sizes.index(max(sizes))]
    lay.extra_blocks = [b for b in blocks if b != main and (b[1] - b[0] + 1) >= 2]
    # Blocks above the main block that are small are preamble (titles, "as at" lines).
    for b in blocks:
        if b[1] < main[0]:
            lay.preamble_rows.extend(i for i in range(b[0], b[1] + 1) if nonblank[i])

    idx = [i for i in range(main[0], main[1] + 1) if nonblank[i]]
    stats = {i: _row_stats(rows[i]) for i in idx}
    # modal populated-cell count among rows after the candidates = typical table width
    widths = [stats[i][0] for i in idx]
    header_at = None
    for pos, i in enumerate(idx[:HEADER_SEARCH_ROWS]):
        n, nonText, text = stats[i]
        following = idx[pos + 1 : pos + 5]
        if n < 2 or not following:
            continue
        mode_w = max(set(widths[pos + 1 :] or widths), key=(widths[pos + 1 :] or widths).count)
        if text >= max(2, int(0.6 * n)) and n >= max(2, int(0.6 * mode_w)):
            if any(stats[j][1] > 0 for j in following):
                header_at = pos
                break
    if header_at is None:
        # no header: table starts at the first row that looks like data (>= 2 cells)
        start = next((p for p, i in enumerate(idx) if stats[i][0] >= 2), 0)
        lay.has_header = False
        lay.preamble_rows.extend(idx[:start])
        data = idx[start:]
    else:
        lay.preamble_rows.extend(idx[:header_at])
        lay.header_rows = [idx[header_at]]
        # optional second header line (units / sub-headings): text-only row right under the header
        nxt = idx[header_at + 1] if header_at + 1 < len(idx) else None
        if nxt is not None and nxt == idx[header_at] + 1:
            n, non_text, text = stats[nxt]
            after = idx[header_at + 2 : header_at + 5]
            if non_text == 0 and text >= 1 and any(stats[j][1] > 0 for j in after):
                lay.header_rows.append(nxt)
        data = [i for i in idx[header_at + 1 :] if i not in lay.header_rows]
    lay.data_rows = data
    first = (lay.header_rows or data or [0])[0]
    last = data[-1] if data else first
    lay.table_range = (first, last)
    lay.blank_rows_skipped = sum(1 for i in range(first, last + 1) if not nonblank[i])

    used = [*lay.header_rows, *data]
    ncols = 0
    for i in used:
        row = rows[i]
        for c in range(len(row) - 1, -1, -1):
            if not is_blank(row[c]):
                ncols = max(ncols, c + 1)
                break
    lay.ncols = ncols
    # headers
    headers: list[str | None] = [None] * ncols
    if lay.header_rows:
        parts: list[list[str]] = [[] for _ in range(ncols)]
        for hr in lay.header_rows:
            expanded = _expand_h_merges(grid, hr, rows[hr])
            for c in range(ncols):
                cell = expanded[c] if c < len(expanded) else None
                if not is_blank(cell):
                    parts[c].append(cell.v.strip())  # type: ignore[union-attr]
        headers = [" ".join(p) if p else None for p in parts]
    lay.headers = headers
    lay.header_synthetic = [h is None for h in headers]
    return lay


def synthetic_header(index: int) -> str:
    return f"Column {col_letter(index)}"
