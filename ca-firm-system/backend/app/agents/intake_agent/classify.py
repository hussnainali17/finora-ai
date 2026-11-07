# ruff: noqa: E501
"""Deterministic classification: column roles, document type, reporting period, currency.

Header synonyms give the first answer; value patterns confirm or override it. Anything below
the confidence threshold is surfaced for review (and optionally sent to the LLM helper)."""

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from app.agents.intake_agent.types import (
    AMOUNT_ROLES,
    CATEGORY_TO_TYPE,
    DATE_ROLES,
    RawCell,
)
from app.agents.intake_agent.values import (
    find_currencies,
    has_ambiguous_symbol,
    is_blank,
    parse_amount,
    parse_date_text,
)

# (role, regex over the lower-cased, punctuation-stripped header). First match wins; order matters.
_SYNONYMS: list[tuple[str, str]] = [
    ("account_code", r"^(a/?c|acc(ount|t)?)\.? ?(code|no|number|#|id)$|^code$|^gl ?code$|^acct$"),
    ("account_name", r"^(account|a/?c|ledger|head)( name| title| description|s)?$|^particulars?$|^account head$"),
    ("value_date", r"value ?date|^val\.? date$"),
    ("date", r"^(txn|transaction|posting|booking|voucher|invoice|bill|entry)?[ _]?date$|^dated?$|^tran date$"),
    ("withdrawal", r"withdraw|^dr\.? amount$|paid out|money out"),
    ("deposit", r"deposit|paid in|money in|^cr\.? amount$"),
    ("debit", r"^(dr|debit|debits)( amount| balance)?$|^debit"),
    ("credit", r"^(cr|credit|credits)( amount| balance)?$|^credit"),
    ("balance", r"balance|closing|running"),
    ("accumulated_depreciation", r"accum.*dep|dep.*accum"),
    ("depreciation", r"depreciation|^dep\.?$"),
    ("net_book_value", r"net book|^nbv$|written down|^wdv$|carrying"),
    ("cost", r"^(asset )?cost|original cost|purchase (cost|price)|gross (cost|value)"),
    ("quantity", r"^(qty|quantity|units?|no of units|on hand|stock)$|qty|quantity"),
    ("unit_cost", r"unit (cost|price|rate)|^rate$|^price$"),
    ("gross_pay", r"gross (pay|salary|wages?)|^gross$"),
    ("deductions", r"deduction|withholding|^tax$"),
    ("net_pay", r"net (pay|salary|wages?)|take home"),
    ("item_code", r"^(sku|item|product|asset|stock)( |_)?(code|no|id|number)$|^sku$|^item$"),
    ("reference", r"ref|voucher|cheque|check ?no|^no\.?$|invoice ?(no|number|#)|^doc"),
    ("party", r"customer|vendor|supplier|payee|party|employee|^name$|beneficiary"),
    ("currency", r"^(currency|ccy|curr)$"),
    ("description", r"descr|narration|details?|remarks?|memo|^item description$|^asset( name)?$"),
    ("amount", r"^amount$|^amt$|value|^total$"),
]  # fmt: skip
_COMPILED = [(role, re.compile(rx)) for role, rx in _SYNONYMS]
_PUNCT = re.compile(r"[^a-z0-9/# ]+")


def normalize_header(h: str | None) -> str:
    if not h:
        return ""
    return re.sub(r"\s+", " ", _PUNCT.sub(" ", h.lower())).strip()


def role_from_header(header: str | None) -> str | None:
    n = normalize_header(header)
    if not n:
        return None
    for role, rx in _COMPILED:
        if rx.search(n):
            return role
    return None


@dataclass
class ColumnProfile:
    index: int
    header: str | None
    n_values: int = 0
    frac_date: float = 0.0
    frac_amount: float = 0.0
    frac_text: float = 0.0
    frac_unique: float = 0.0
    avg_len: float = 0.0
    sample: list[str] = field(default_factory=list)
    all_text: list[str] = field(default_factory=list)


def profile_column(index: int, header: str | None, cells: list[RawCell | None]) -> ColumnProfile:
    vals = [c for c in cells if c is not None and not is_blank(c)]
    p = ColumnProfile(index, header, n_values=len(vals))
    if not vals:
        return p
    d = a = t = 0
    for c in vals:
        if c.t == "d":
            d += 1
        elif c.t == "n":
            a += 1
        elif parse_date_text(c.v).status in ("ok", "ambiguous") and len(c.v) >= 6:
            d += 1
        elif parse_amount(c).status == "ok":
            a += 1
        else:
            t += 1
    n = len(vals)
    p.frac_date, p.frac_amount, p.frac_text = d / n, a / n, t / n
    p.frac_unique = len({c.v for c in vals}) / n
    p.avg_len = sum(len(c.v) for c in vals) / n
    p.sample = [c.v for c in vals[:5]]
    p.all_text = [c.v for c in vals]
    return p


@dataclass
class RoleGuess:
    role: str
    confidence: float
    source: str  # header | content | combined | none


def guess_role(p: ColumnProfile) -> RoleGuess:
    by_header = role_from_header(p.header)
    if p.n_values == 0:
        return RoleGuess("ignore", 0.5, "none")
    kind = (
        "date" if p.frac_date >= 0.8
        else "amount" if p.frac_amount >= 0.8
        else "text" if p.frac_text >= 0.6
        else "mixed"
    )  # fmt: skip
    if by_header:
        compatible = (
            (by_header in DATE_ROLES and kind == "date")
            or (by_header in AMOUNT_ROLES and kind == "amount")
            or (by_header not in DATE_ROLES | AMOUNT_ROLES and kind in ("text", "mixed", "amount"))
        )
        if by_header in {"account_code", "reference", "item_code"} and kind == "amount":
            compatible = True  # numeric-looking codes are still codes
        if compatible:
            return RoleGuess(by_header, 0.95, "header")
        return RoleGuess(by_header, 0.5, "combined")  # header and values disagree -> review
    if kind == "date":
        return RoleGuess("date", 0.7, "content")
    if kind == "amount":
        return RoleGuess("amount", 0.45, "content")
    if kind == "text" and p.avg_len > 12:
        return RoleGuess("description", 0.6, "content")
    return RoleGuess("other", 0.3, "none")


# ------------------------------------------------------------------------------- document type

_TYPE_RULES: dict[str, dict[str, Any]] = {
    "trial_balance": {"need": [{"debit"}, {"credit"}], "any": [{"account_name", "account_code"}],
                      "forbid": {"date", "withdrawal", "deposit", "balance"}},
    "bank_statement": {"need": [{"date"}, {"withdrawal", "deposit", "debit", "credit", "amount"}],
                       "any": [{"balance", "description"}], "forbid": set()},
    "general_ledger": {"need": [{"date"}, {"debit"}, {"credit"}], "any": [{"account_name", "account_code", "description"}],
                       "forbid": {"withdrawal", "deposit"}},
    "fixed_asset_register": {"need": [{"cost", "net_book_value", "accumulated_depreciation", "depreciation"}],
                             "any": [{"description", "item_code", "account_name"}], "forbid": {"gross_pay"}},
    "inventory_report": {"need": [{"quantity"}], "any": [{"unit_cost", "item_code", "description"}],
                         "forbid": {"gross_pay", "debit", "credit"}},
    "payroll_schedule": {"need": [{"gross_pay", "net_pay", "deductions"}], "any": [{"party", "description"}],
                         "forbid": {"debit", "credit"}},
    "sales_ledger": {"need": [{"date"}, {"amount", "debit", "credit"}], "any": [{"party"}], "forbid": set()},
    "purchase_ledger": {"need": [{"date"}, {"amount", "debit", "credit"}], "any": [{"party"}], "forbid": set()},
}  # fmt: skip


def score_document_type(roles: set[str], category_type: str | None) -> tuple[str, float]:
    best, best_score = "unknown", 0.0
    for dtype in ("trial_balance", "bank_statement", "general_ledger", "fixed_asset_register",
                  "inventory_report", "payroll_schedule"):  # fmt: skip
        rule = _TYPE_RULES[dtype]
        if rule["forbid"] & roles:
            continue
        needs = rule["need"]
        met = sum(1 for group in needs if group & roles)
        if met < len(needs):
            continue
        anys = rule["any"]
        extra = sum(1 for g in anys if g & roles)
        score = 0.6 + 0.1 * min(2, len(needs)) + 0.1 * extra
        if category_type == dtype:
            score += 0.1
        if score > best_score:
            best, best_score = dtype, score
    return best, min(best_score, 0.95)


# ------------------------------------------------------------------------------- preamble


_AS_AT = re.compile(
    r"(?i)\b(as (at|on)|up ?to|ended?|ending|for the (year|period|month|quarter) ended?)\b[ :]*(.+)"
)
_RANGE = re.compile(r"(?i)\b(from|period)\b[ :]*(.+?)\b(to|-|–|until|through)\b[ :]*(.+)")


@dataclass
class PreambleInfo:
    period_start: date | None = None
    period_end: date | None = None
    currency: str | None = None
    ambiguous_currency: bool = False
    title: str | None = None


def _date_in(text: str, order: str = "DMY") -> date | None:
    for rx in (
        r"\d{4}[-/.]\d{1,2}[-/.]\d{1,2}",
        r"\d{1,2}[ \-./]?[A-Za-z]{3,9}\.?[ \-.,/]*\d{2,4}",
        r"[A-Za-z]{3,9}\.? \d{1,2}(st|nd|rd|th)?,? \d{4}",
        r"\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4}",
    ):
        m = re.search(rx, text)
        if m:
            r = parse_date_text(m.group(0), order)
            if r.status in ("ok", "ambiguous") and r.value:
                return r.value
    return None


def scan_preamble(lines: list[str], ordered_default: str = "DMY") -> PreambleInfo:
    info = PreambleInfo()
    currencies: set[str] = set()
    for ln in lines:
        if info.title is None and len(ln) > 3 and not _date_in(ln):
            info.title = ln[:200]
        currencies |= find_currencies(ln)
        if has_ambiguous_symbol(ln):
            info.ambiguous_currency = True
        if m := _RANGE.search(ln):
            s, e = _date_in(m.group(2), ordered_default), _date_in(m.group(4), ordered_default)
            if s and e:
                info.period_start, info.period_end = s, e
                continue
        if m := _AS_AT.search(ln):
            d = _date_in(m.group(m.lastindex or 0), ordered_default)
            if d:
                info.period_end = d
    if len(currencies) == 1:
        info.currency = next(iter(currencies))
    return info


def category_type(category: str | None) -> str | None:
    return CATEGORY_TO_TYPE.get(category or "")
