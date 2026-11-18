"""General Ledger reconciliation module (Agent 2).

Checks performed:
1. Debit/Credit balance per account (each account's total Dr == total Cr after netting).
2. Duplicate transaction detection (same date + amount + description).
3. Out-of-period entry detection.
4. Missing mandatory fields (date, debit or credit, account name).
5. GL ↔ Trial Balance reconciliation: for each account that appears in both, the
   net GL balance must match the TB closing balance within tolerance.
6. Large/unusual transaction flagging (> 2 std-dev from account mean).

All arithmetic uses Python Decimal. No LLM calls; findings are deterministic.
Source references (document_id, table_id, row_index) are preserved on every finding.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

from app.accounting.reconciliation._types import (
    FindingData,
    ReconciliationResult,
    ScheduleData,
)

logger = logging.getLogger("app.accounting.reconciliation.general_ledger")

TOLERANCE = Decimal("0.01")
LARGE_TX_SIGMA = Decimal("2")  # flag transactions > mean + 2*σ


def _dec(val: Any) -> Decimal:
    """Safe Decimal conversion; returns 0 on failure."""
    if val is None:
        return Decimal("0")
    try:
        return Decimal(str(val).strip().replace(",", ""))
    except InvalidOperation:
        return Decimal("0")


def _str(val: Any) -> str:
    return str(val).strip() if val is not None else ""


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def check_general_ledger(
    gl_tables: list[dict[str, Any]],
    tb_tables: list[dict[str, Any]],
    period_start: Any,
    period_end: Any,
) -> ReconciliationResult:
    """Run all GL checks and return findings + schedules.

    Args:
        gl_tables: Extracted tables whose detected/confirmed type is "general_ledger".
                   Each dict has keys: table_id, document_id, detected_type,
                   confirmed_type, period_start, period_end, rows (list of normalized dicts).
        tb_tables: Extracted tables whose type is "trial_balance" (may be empty).
        period_start: Expected period start date (date | None).
        period_end:   Expected period end date (date | None).

    Returns:
        ReconciliationResult with findings and a GL summary schedule.
    """
    findings: list[FindingData] = []
    schedules: list[ScheduleData] = []

    if not gl_tables:
        return ReconciliationResult(findings=[], schedules=[], summary={
            "total_findings": 0, "gl_rows": 0, "accounts": 0,
            "note": "No GL tables available for this period.",
        })

    # Collect all GL rows with traceable source_ref
    gl_rows = _collect_rows(gl_tables)
    logger.info("GL check: %d rows collected from %d tables", len(gl_rows), len(gl_tables))

    if not gl_rows:
        return ReconciliationResult(findings=[], schedules=[], summary={
            "total_findings": 0, "gl_rows": 0, "accounts": 0,
        })

    # 1. Missing fields
    findings.extend(_check_missing_fields(gl_rows))

    # 2. Out-of-period entries
    if period_start and period_end:
        findings.extend(_check_out_of_period(gl_rows, period_start, period_end))

    # 3. Duplicate transaction detection
    findings.extend(_check_duplicates(gl_rows))

    # 4. Per-account aggregation (used for balance check and large-tx flag)
    account_totals = _aggregate_by_account(gl_rows)

    # 5. Large/unusual transactions
    findings.extend(_check_large_transactions(gl_rows, account_totals))

    # 6. GL ↔ TB reconciliation
    if tb_tables:
        tb_balances = _extract_tb_balances(tb_tables)
        recon_findings, recon_schedule = _reconcile_gl_vs_tb(account_totals, tb_balances)
        findings.extend(recon_findings)
        schedules.append(recon_schedule)

    # 7. GL summary schedule (account-level net balances with source traceability)
    gl_summary_rows = []
    for acct_key, data in sorted(account_totals.items()):
        net = data.total_debit - data.total_credit
        gl_summary_rows.append({
            "account_code": data.account_code,
            "account_name": data.account_name,
            "total_debit": str(data.total_debit),
            "total_credit": str(data.total_credit),
            "net_balance": str(net),
            "tx_count": data.tx_count,
            "source_document_ids": list(data.source_document_ids),
            "source_table_ids": list(data.source_table_ids),
        })

    total_gl_dr = sum(d.total_debit for d in account_totals.values())
    total_gl_cr = sum(d.total_credit for d in account_totals.values())
    is_balanced = abs(total_gl_dr - total_gl_cr) <= TOLERANCE

    if not is_balanced:
        findings.append(FindingData(
            finding_type="gl_out_of_balance",
            severity="error",
            title="General Ledger is Out of Balance",
            description=(
                f"Total GL debits ({total_gl_dr}) do not equal total GL credits ({total_gl_cr}). "
                f"Difference: {abs(total_gl_dr - total_gl_cr)}. "
                "This may indicate missing transactions or data extraction errors."
            ),
            source_ref={"module": "general_ledger"},
            amount=abs(total_gl_dr - total_gl_cr),
            currency=None,
        ))

    schedules.append(ScheduleData(
        schedule_type="gl_account_summary",
        label="General Ledger — Account-Level Summary",
        data={
            "accounts": gl_summary_rows,
            "total_debit": str(total_gl_dr),
            "total_credit": str(total_gl_cr),
            "is_balanced": is_balanced,
            "tx_count": len(gl_rows),
        },
        source_refs=[
            {"document_id": t["document_id"], "table_id": t["table_id"]}
            for t in gl_tables
        ],
    ))

    by_severity = defaultdict(int)
    for f in findings:
        by_severity[f.severity] += 1

    return ReconciliationResult(
        findings=findings,
        schedules=schedules,
        summary={
            "total_findings": len(findings),
            "by_severity": dict(by_severity),
            "gl_rows": len(gl_rows),
            "accounts": len(account_totals),
            "total_debit": str(total_gl_dr),
            "total_credit": str(total_gl_cr),
            "is_balanced": is_balanced,
        },
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _collect_rows(tables: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Flatten all rows from all GL tables, adding source traceability."""
    out: list[dict[str, Any]] = []
    for t in tables:
        doc_id = t.get("document_id", "")
        tbl_id = t.get("table_id", "")
        for row in t.get("rows", []):
            out.append({
                **row,
                "_source_doc": doc_id,
                "_source_table": tbl_id,
            })
    return out


def _check_missing_fields(rows: list[dict[str, Any]]) -> list[FindingData]:
    findings: list[FindingData] = []
    for row in rows:
        missing = []
        # A GL row needs at least a date and one monetary column
        if not _str(row.get("date") or row.get("value_date")):
            missing.append("date")
        has_amount = any(
            row.get(k) for k in ("debit", "credit", "amount", "withdrawal", "deposit")
        )
        if not has_amount:
            missing.append("debit/credit amount")
        if missing:
            findings.append(FindingData(
                finding_type="gl_missing_field",
                severity="warning",
                title=f"GL row missing: {', '.join(missing)}",
                description=(
                    f"Row {row.get('_row_index', '?')} is missing required field(s): "
                    f"{', '.join(missing)}."
                ),
                source_ref={
                    "document_id": row.get("_source_doc"),
                    "table_id": row.get("_source_table"),
                    "row_index": row.get("_row_index"),
                },
            ))
    return findings


def _check_out_of_period(
    rows: list[dict[str, Any]], period_start: Any, period_end: Any
) -> list[FindingData]:
    from datetime import date as date_type
    findings: list[FindingData] = []
    for row in rows:
        raw_date = _str(row.get("date") or row.get("value_date") or "")
        if not raw_date:
            continue
        try:
            if isinstance(raw_date, date_type):
                tx_date = raw_date
            else:
                tx_date = date_type.fromisoformat(raw_date[:10])
        except (ValueError, TypeError):
            continue
        if not (period_start <= tx_date <= period_end):
            findings.append(FindingData(
                finding_type="gl_out_of_period",
                severity="warning",
                title=f"GL transaction dated {tx_date} is outside the accounting period",
                description=(
                    f"Transaction on {tx_date} (row {row.get('_row_index', '?')}) falls outside "
                    f"the period {period_start} to {period_end}. "
                    "It may be a cut-off error or mis-posted entry."
                ),
                source_ref={
                    "document_id": row.get("_source_doc"),
                    "table_id": row.get("_source_table"),
                    "row_index": row.get("_row_index"),
                    "tx_date": str(tx_date),
                },
            ))
    return findings


def _check_duplicates(rows: list[dict[str, Any]]) -> list[FindingData]:
    """Flag rows that share the same (date, debit, credit, description) tuple."""
    seen: dict[tuple, list[int]] = defaultdict(list)
    for i, row in enumerate(rows):
        key = (
            _str(row.get("date") or row.get("value_date") or ""),
            _str(row.get("debit") or row.get("withdrawal") or ""),
            _str(row.get("credit") or row.get("deposit") or ""),
            _str(row.get("description") or row.get("account_name") or "")[:80],
        )
        if any(key):
            seen[key].append(i)

    findings: list[FindingData] = []
    for key, idxs in seen.items():
        if len(idxs) < 2:
            continue
        first = rows[idxs[0]]
        findings.append(FindingData(
            finding_type="gl_duplicate_transaction",
            severity="warning",
            title="Possible duplicate GL transaction",
            description=(
                f"{len(idxs)} rows share the same date ({key[0]}), debit ({key[1]}), "
                f"credit ({key[2]}) and description. They may be duplicate postings. "
                f"Row indices: {[rows[i].get('_row_index') for i in idxs]}."
            ),
            source_ref={
                "document_id": first.get("_source_doc"),
                "table_id": first.get("_source_table"),
                "row_indices": [rows[i].get("_row_index") for i in idxs],
            },
        ))
    return findings


@dataclass
class _AcctData:
    account_code: str = ""
    account_name: str = ""
    total_debit: Decimal = field(default_factory=lambda: Decimal("0"))
    total_credit: Decimal = field(default_factory=lambda: Decimal("0"))
    tx_count: int = 0
    tx_amounts: list[Decimal] = field(default_factory=list)
    source_document_ids: set[str] = field(default_factory=set)
    source_table_ids: set[str] = field(default_factory=set)


def _aggregate_by_account(rows: list[dict[str, Any]]) -> dict[str, _AcctData]:
    accounts: dict[str, _AcctData] = {}
    for row in rows:
        code = _str(row.get("account_code") or row.get("reference") or "")
        name = _str(row.get("account_name") or row.get("description") or "")
        key = code or name or "UNKNOWN"
        if key not in accounts:
            accounts[key] = _AcctData(account_code=code, account_name=name)
        a = accounts[key]
        dr = _dec(row.get("debit") or row.get("withdrawal") or 0)
        cr = _dec(row.get("credit") or row.get("deposit") or 0)
        amt = _dec(row.get("amount") or 0)
        # If only "amount" is present, treat as debit by default (flag is raised elsewhere)
        if dr == 0 and cr == 0 and amt != 0:
            dr = amt
        a.total_debit += dr
        a.total_credit += cr
        a.tx_count += 1
        a.tx_amounts.append(dr + cr)
        if row.get("_source_doc"):
            a.source_document_ids.add(str(row["_source_doc"]))
        if row.get("_source_table"):
            a.source_table_ids.add(str(row["_source_table"]))
    return accounts


def _check_large_transactions(
    rows: list[dict[str, Any]], account_totals: dict[str, _AcctData]
) -> list[FindingData]:
    """Flag individual transactions > mean + LARGE_TX_SIGMA * std_dev per account."""
    import math
    findings: list[FindingData] = []

    # Build per-account stats
    stats: dict[str, tuple[Decimal, Decimal]] = {}  # key -> (mean, std_dev)
    for key, data in account_totals.items():
        amts = data.tx_amounts
        if len(amts) < 3:
            continue  # not enough data for meaningful statistics
        n = len(amts)
        mean = sum(amts) / n
        variance = sum((a - mean) ** 2 for a in amts) / n
        std = Decimal(str(math.sqrt(float(variance))))
        stats[key] = (mean, std)

    for row in rows:
        code = _str(row.get("account_code") or row.get("reference") or "")
        name = _str(row.get("account_name") or row.get("description") or "")
        key = code or name or "UNKNOWN"
        if key not in stats:
            continue
        mean, std = stats[key]
        if std == 0:
            continue
        dr = _dec(row.get("debit") or row.get("withdrawal") or 0)
        cr = _dec(row.get("credit") or row.get("deposit") or 0)
        tx_amt = dr + cr
        threshold = mean + LARGE_TX_SIGMA * std
        if tx_amt > threshold:
            findings.append(FindingData(
                finding_type="gl_large_transaction",
                severity="warning",
                title=f"Unusually large GL transaction for account '{name or code}'",
                description=(
                    f"Row {row.get('_row_index', '?')}: amount {tx_amt} exceeds "
                    f"the account mean ({mean:.2f}) by more than {LARGE_TX_SIGMA}σ "
                    f"(threshold {threshold:.2f}). Please verify this transaction."
                ),
                source_ref={
                    "document_id": row.get("_source_doc"),
                    "table_id": row.get("_source_table"),
                    "row_index": row.get("_row_index"),
                },
                amount=tx_amt,
            ))
    return findings


def _extract_tb_balances(tb_tables: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Build a {account_key: {code, name, net_debit, net_credit}} map from TB tables."""
    balances: dict[str, dict[str, Any]] = {}
    for t in tb_tables:
        for row in t.get("rows", []):
            code = _str(row.get("account_code") or row.get("code") or row.get("reference") or "")
            name = _str(row.get("account_name") or row.get("description") or row.get("name") or "")
            key = code or name or "UNKNOWN"
            dr = _dec(row.get("debit") or 0)
            cr = _dec(row.get("credit") or 0)
            if key in balances:
                balances[key]["net_debit"] += dr
                balances[key]["net_credit"] += cr
            else:
                balances[key] = {
                    "account_code": code,
                    "account_name": name,
                    "net_debit": dr,
                    "net_credit": cr,
                    "source_refs": [{"document_id": t.get("document_id"), "table_id": t.get("table_id")}],
                }
    return balances


def _reconcile_gl_vs_tb(
    account_totals: dict[str, _AcctData],
    tb_balances: dict[str, dict[str, Any]],
) -> tuple[list[FindingData], ScheduleData]:
    """Compare GL net balances with TB balances account by account."""
    findings: list[FindingData] = []
    recon_rows: list[dict[str, Any]] = []
    matched = set()

    for key, gl_data in account_totals.items():
        gl_net = gl_data.total_debit - gl_data.total_credit
        tb_entry = tb_balances.get(key)
        if tb_entry is None:
            # Try matching by name fragment
            for tb_key, tb_val in tb_balances.items():
                if gl_data.account_name and gl_data.account_name.lower() in tb_key.lower():
                    tb_entry = tb_val
                    break
        if tb_entry is None:
            # Account in GL but not in TB
            recon_rows.append({
                "account_code": gl_data.account_code,
                "account_name": gl_data.account_name,
                "gl_net": str(gl_net),
                "tb_net": None,
                "difference": str(gl_net),
                "status": "gl_only",
            })
            if abs(gl_net) > TOLERANCE:
                findings.append(FindingData(
                    finding_type="gl_account_not_in_tb",
                    severity="warning",
                    title=f"GL account '{gl_data.account_name or gl_data.account_code}' not found in Trial Balance",
                    description=(
                        f"This account has a net GL balance of {gl_net} but no matching "
                        "entry exists in the Trial Balance. It may be a new account or a "
                        "data extraction discrepancy."
                    ),
                    source_ref={
                        "gl_table_ids": list(gl_data.source_table_ids),
                        "document_ids": list(gl_data.source_document_ids),
                    },
                    amount=abs(gl_net),
                ))
        else:
            matched.add(key)
            tb_net = tb_entry["net_debit"] - tb_entry["net_credit"]
            diff = gl_net - tb_net
            status = "matched" if abs(diff) <= TOLERANCE else "discrepancy"
            recon_rows.append({
                "account_code": gl_data.account_code,
                "account_name": gl_data.account_name,
                "gl_net": str(gl_net),
                "tb_net": str(tb_net),
                "difference": str(diff),
                "status": status,
            })
            if abs(diff) > TOLERANCE:
                findings.append(FindingData(
                    finding_type="gl_tb_discrepancy",
                    severity="error",
                    title=f"GL vs TB discrepancy for '{gl_data.account_name or gl_data.account_code}'",
                    description=(
                        f"GL net balance ({gl_net}) differs from Trial Balance net balance ({tb_net}) "
                        f"by {abs(diff)}. This may indicate unposted journal entries or data discrepancies."
                    ),
                    source_ref={
                        "gl_table_ids": list(gl_data.source_table_ids),
                        "tb_source_refs": tb_entry.get("source_refs", []),
                    },
                    amount=abs(diff),
                ))

    # Accounts in TB but not in GL
    for key, tb_entry in tb_balances.items():
        if key in matched:
            continue
        tb_net = tb_entry["net_debit"] - tb_entry["net_credit"]
        recon_rows.append({
            "account_code": tb_entry["account_code"],
            "account_name": tb_entry["account_name"],
            "gl_net": None,
            "tb_net": str(tb_net),
            "difference": str(-tb_net),
            "status": "tb_only",
        })
        if abs(tb_net) > TOLERANCE:
            findings.append(FindingData(
                finding_type="tb_account_not_in_gl",
                severity="info",
                title=f"TB account '{tb_entry['account_name'] or tb_entry['account_code']}' has no GL transactions",
                description=(
                    f"This account appears in the Trial Balance (net {tb_net}) but has no "
                    "matching General Ledger transactions. This may be expected for opening "
                    "balances or summary accounts."
                ),
                source_ref={"tb_source_refs": tb_entry.get("source_refs", [])},
                amount=abs(tb_net),
            ))

    schedule = ScheduleData(
        schedule_type="gl_tb_reconciliation",
        label="GL vs Trial Balance Reconciliation",
        data={"rows": recon_rows},
        source_refs=[],
    )
    return findings, schedule


__all__ = ["check_general_ledger"]
