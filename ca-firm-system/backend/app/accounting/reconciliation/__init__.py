"""Shared types for all reconciliation modules.

All monetary amounts use ``Decimal`` — never float. The rule is enforced here
by declaring ``FindingData.amount`` as ``Decimal | None``.

Reconciliation modules receive extracted rows (list of dicts with normalized
column-role keys: "date", "amount", "reference", "description", etc.) and
return a ``ReconciliationResult`` containing:

- ``findings``: list of individual issues found
- ``schedules``: list of structured output schedules (ageing, recon, movement etc.)
- ``summary``: module-level counts and totals

Imports:
    from app.accounting.reconciliation import (
        FindingData, ScheduleData, ReconciliationResult,
        check_sales_receivables, check_purchases_payables,
        check_bank_cash, check_inventory, check_fixed_assets, check_payroll,
    )
"""

from app.accounting.reconciliation._types import FindingData, ReconciliationResult, ScheduleData
from app.accounting.reconciliation.bank_cash import check_bank_cash
from app.accounting.reconciliation.fixed_assets import check_fixed_assets
from app.accounting.reconciliation.inventory import check_inventory
from app.accounting.reconciliation.payroll import check_payroll
from app.accounting.reconciliation.purchases_payables import check_purchases_payables
from app.accounting.reconciliation.sales_receivables import check_sales_receivables

__all__ = [
    "FindingData",
    "ScheduleData",
    "ReconciliationResult",
    "check_sales_receivables",
    "check_purchases_payables",
    "check_bank_cash",
    "check_inventory",
    "check_fixed_assets",
    "check_payroll",
]
