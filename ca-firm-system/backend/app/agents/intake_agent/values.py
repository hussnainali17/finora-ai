"""Deterministic value parsing: dates, amounts, text and currency. No LLM, no guessing: anything
that cannot be read unambiguously is reported, never silently converted."""

import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation

from app.agents.intake_agent.types import RawCell

AMOUNT_QUANT = Decimal("0.0001")
_MONTHS = {
    m: i
    for i, names in enumerate(
        [
            ("jan", "january"), ("feb", "february"), ("mar", "march"), ("apr", "april"),
            ("may",), ("jun", "june"), ("jul", "july"), ("aug", "august"),
            ("sep", "sept", "september"), ("oct", "october"), ("nov", "november"),
            ("dec", "december"),
        ],
        start=1,
    )
    for m in names
}  # fmt: skip
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f​‎‏﻿]")

ISO_CURRENCIES = frozenset(
    "PKR USD EUR GBP AED SAR INR CAD AUD CNY JPY CHF QAR KWD BHD OMR TRY BDT LKR NPR MYR "
    "SGD".split()
)
_CURRENCY_WORD = re.compile(r"\b(" + "|".join(sorted(ISO_CURRENCIES)) + r")\b", re.IGNORECASE)
_AMOUNT_NOISE = re.compile(
    r"(?i)(?<![a-z])(rs|pkr|usd|eur|gbp|aed|sar|inr|cad|aud)(?![a-z])\.?|[$£€¥]|\u00a0|\s"
)
# Thousands grouping: international (1,234,567) or lakh/crore (12,34,567).
_GROUPED = re.compile(r"^\d{1,3}(,\d{3})+(\.\d+)?$|^\d{1,2}(,\d{2})+,\d{3}(\.\d+)?$")
_GROUPED_EU = re.compile(r"^\d{1,3}(\.\d{3})+(,\d+)?$|^\d{1,2}(\.\d{2})+\.\d{3}(,\d+)?$")


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    text = unicodedata.normalize("NFC", value)
    text = _CONTROL.sub("", text)
    return re.sub(r"\s+", " ", text).strip()


def is_blank(cell: RawCell | None) -> bool:
    return cell is None or cell.v.strip() == ""


# ------------------------------------------------------------------------------ amounts


@dataclass(frozen=True)
class AmountResult:
    status: str  # ok | blank | invalid
    value: Decimal | None = None
    note: str | None = None  # info about an interpretation applied (e.g. "Cr suffix")


_DOT_STYLE = re.compile(r"^-?\(?\d{1,3}(,\d{3})+(\.\d+)?\)?$")
_COMMA_STYLE = re.compile(r"^-?\(?\d{1,3}(\.\d{3})+(,\d+)?\)?$|^-?\(?\d+,\d{1,2}\)?$")


def detect_decimal_style(values: list[str]) -> str:
    """'dot' (1,234.50) or 'comma' (1.234,50), decided from the whole column, never per cell."""
    dot = comma = 0
    for raw in values:
        s = _AMOUNT_NOISE.sub("", raw).rstrip("-").rstrip("CcRrDd")
        if _DOT_STYLE.match(s) or re.match(r"^-?\(?\d+\.\d+\)?$", s):
            dot += 1
        elif _COMMA_STYLE.match(s):
            comma += 1
    return "comma" if comma > dot else "dot"


def parse_amount(cell: RawCell | None, style: str = "dot") -> AmountResult:
    if cell is None or cell.v.strip() == "":
        return AmountResult("blank")
    if cell.t == "n":
        try:
            return AmountResult("ok", _quantize(Decimal(cell.v)))
        except InvalidOperation:
            return AmountResult("invalid")
    if cell.t in ("b", "e", "d"):
        return AmountResult("invalid", note=f"{cell.t}-type cell")
    text = cell.v.strip()
    if text in {"-", "–", "—", "nil", "Nil", "NIL"}:
        return AmountResult("blank")  # accounting "no amount" marker; not guessed as zero
    note = None
    s = _AMOUNT_NOISE.sub("", text)
    negative = False
    m = re.search(r"(?i)(dr|cr)\.?$", s)
    if m:
        negative = m.group(1).lower() == "cr"
        note = f"{m.group(1).upper()} suffix: Dr positive, Cr negative"
        s = s[: m.start()]
    if s.startswith("(") and s.endswith(")"):
        negative, s = not negative if note else True, s[1:-1]
    if s.endswith("-"):
        negative, s = True, s[:-1]
    if s.startswith(("-", "−")):
        negative, s = True, s[1:]
    elif s.startswith("+"):
        s = s[1:]
    if style == "comma":
        if "." in s and not _GROUPED_EU.match(s):
            return AmountResult("invalid")
        s = s.replace(".", "").replace(",", ".")
    else:
        if "," in s and not _GROUPED.match(s):
            return AmountResult("invalid")
        s = s.replace(",", "")
    if not re.fullmatch(r"\d+(\.\d+)?|\.\d+", s):
        return AmountResult("invalid")
    try:
        value = Decimal(s)
    except InvalidOperation:
        return AmountResult("invalid")
    return AmountResult("ok", _quantize(-value if negative else value), note)


def _quantize(d: Decimal) -> Decimal:
    q = d.quantize(AMOUNT_QUANT, rounding=ROUND_HALF_EVEN)
    return q + 0 if q == 0 else q  # avoid "-0.0000"


def amount_str(d: Decimal) -> str:
    """Plain, fixed-point string with at least 2 decimals (e.g. 1234.5 -> '1234.50')."""
    s = format(d, "f")
    if "." in s:
        s = s.rstrip("0")
        if len(s.split(".")[1]) < 2:
            s = s + "0" * (2 - len(s.split(".")[1]))
    else:
        s += ".00"
    return s


# ------------------------------------------------------------------------------ dates

_NUMERIC_DATE = re.compile(r"^(\d{1,2})[/\-. ](\d{1,2})[/\-. ](\d{2}|\d{4})$")
_YMD = re.compile(r"^(\d{4})[/\-.](\d{1,2})[/\-.](\d{1,2})$")
_D_MON_Y = re.compile(r"^(\d{1,2})[ \-./]?([A-Za-z]{3,9})\.?[ \-.,/]*(\d{2}|\d{4})$")
_MON_D_Y = re.compile(r"^([A-Za-z]{3,9})\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})$")
_COMPACT = re.compile(r"^(\d{4})(\d{2})(\d{2})$")


@dataclass(frozen=True)
class DateResult:
    status: str  # ok | blank | invalid | ambiguous
    value: date | None = None  # for 'ambiguous': the reading under the caller's default order
    alt: date | None = None  # the other reading, when ambiguous
    certain_order: str | None = None  # 'DMY' / 'MDY' when this value alone proves the order


def _year(y: str) -> int:
    n = int(y)
    return n if len(y) == 4 else (2000 + n if n <= 69 else 1900 + n)


def _mk(y: int, m: int, d: int) -> date | None:
    try:
        return date(y, m, d)
    except ValueError:
        return None


def parse_date(cell: RawCell | None, order: str = "DMY") -> DateResult:
    if cell is None or cell.v.strip() == "":
        return DateResult("blank")
    if cell.t == "d":
        try:
            return DateResult("ok", datetime.fromisoformat(cell.v).date())
        except ValueError:
            return DateResult("invalid")
    if cell.t in ("b", "e"):
        return DateResult("invalid")
    return parse_date_text(cell.v, order)


def parse_date_text(text: str, order: str = "DMY") -> DateResult:
    s = text.strip()
    if m := _YMD.match(s):
        d = _mk(int(m[1]), int(m[2]), int(m[3]))
        return DateResult("ok", d) if d else DateResult("invalid")
    if m := _COMPACT.match(s):
        d = _mk(int(m[1]), int(m[2]), int(m[3]))
        return DateResult("ok", d) if d else DateResult("invalid")
    if m := _D_MON_Y.match(s):
        mon = _MONTHS.get(m[2].lower())
        d = _mk(_year(m[3]), mon, int(m[1])) if mon else None
        return DateResult("ok", d) if d else DateResult("invalid")
    if m := _MON_D_Y.match(s):
        mon = _MONTHS.get(m[1].lower())
        d = _mk(int(m[3]), mon, int(m[2])) if mon else None
        return DateResult("ok", d) if d else DateResult("invalid")
    if m := _NUMERIC_DATE.match(s):
        a, b, y = int(m[1]), int(m[2]), _year(m[3])
        dmy, mdy = _mk(y, b, a), _mk(y, a, b)
        if a > 12:  # first number cannot be a month => day-first
            return DateResult("ok", dmy, certain_order="DMY") if dmy else DateResult("invalid")
        if b > 12:  # second number cannot be a month => month-first
            return DateResult("ok", mdy, certain_order="MDY") if mdy else DateResult("invalid")
        if a == b:
            return DateResult("ok", dmy) if dmy else DateResult("invalid")
        first, other = (dmy, mdy) if order == "DMY" else (mdy, dmy)
        if first is None:
            return DateResult("invalid")
        return DateResult("ambiguous", first, other)
    return DateResult("invalid")


EXCEL_EPOCH = date(1899, 12, 30)


def excel_serial_to_date(serial: Decimal) -> date | None:
    if serial != serial.to_integral_value() or not (20000 <= serial <= 80000):
        return None
    return EXCEL_EPOCH + timedelta(days=int(serial))


# ------------------------------------------------------------------------------ currency


def find_currencies(text: str) -> set[str]:
    """ISO codes (PKR, USD, ...) and unambiguous symbols. '$' and 'Rs' are NOT mapped: they are
    shared by several currencies and guessing would be wrong."""
    found = {m.upper() for m in _CURRENCY_WORD.findall(text)}
    if "€" in text:
        found.add("EUR")
    if "£" in text:
        found.add("GBP")
    return found


def has_ambiguous_symbol(text: str) -> bool:
    return bool(re.search(r"\$|\bRs\.?\b", text))
