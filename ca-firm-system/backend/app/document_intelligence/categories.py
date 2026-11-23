"""Module-specific document category registries and validation definitions.

Supports:
- Accounting (10 categories, preserved exactly)
- Taxation (7 categories)
- Audit (extensible categories)
"""

from __future__ import annotations

from typing import Any, Literal

ModuleType = Literal["accounting", "taxation", "audit", "general"]

# -----------------------------------------------------------------------------
# Module Categories
# -----------------------------------------------------------------------------

ACCOUNTING_CATEGORIES: list[tuple[str, str]] = [
    ("trial_balance", "Trial Balance (TB)"),
    ("general_ledger", "General Ledger (GL)"),
    ("bank_statement", "Bank Statement"),
    ("invoice", "Invoice"),
    ("receipt", "Receipt"),
    ("contract", "Contract"),
    ("fixed_asset_schedule", "Fixed Asset Schedule"),
    ("inventory_report", "Inventory Report"),
    ("payroll_schedule", "Payroll Schedule"),
    ("other", "Other"),
]

TAXATION_CATEGORIES: list[tuple[str, str]] = [
    ("tax_return", "Tax Return"),
    ("withholding_certificate", "Withholding Certificate"),
    ("sales_tax_return", "Sales Tax Return"),
    ("tax_payment_challan", "Tax Payment Challan"),
    ("tax_notice", "Tax Notice"),
    ("tax_exemption_certificate", "Tax Exemption Certificate"),
    ("tax_other", "Other"),
]

AUDIT_CATEGORIES: list[tuple[str, str]] = [
    ("audit_engagement_letter", "Audit Engagement Letter"),
    ("management_representation", "Management Representation Letter"),
    ("audit_confirmation", "Audit Confirmation"),
    ("sampling_evidence", "Sampling Evidence"),
    ("audit_other", "Other"),
]

MODULE_CATEGORIES_MAP: dict[str, list[tuple[str, str]]] = {
    "accounting": ACCOUNTING_CATEGORIES,
    "taxation": TAXATION_CATEGORIES,
    "audit": AUDIT_CATEGORIES,
    "general": [("other", "Other")],
}

ACCOUNTING_CATEGORY_KEYS = frozenset(k for k, _ in ACCOUNTING_CATEGORIES)
TAXATION_CATEGORY_KEYS = frozenset(k for k, _ in TAXATION_CATEGORIES)
AUDIT_CATEGORY_KEYS = frozenset(k for k, _ in AUDIT_CATEGORIES)

ALL_CATEGORIES: tuple[str, ...] = tuple(
    sorted(ACCOUNTING_CATEGORY_KEYS | TAXATION_CATEGORY_KEYS | AUDIT_CATEGORY_KEYS)
)


def get_categories_for_module(module: str) -> list[tuple[str, str]]:
    """Returns valid (category_key, label) tuples for the specified module."""
    return MODULE_CATEGORIES_MAP.get(module.lower(), ACCOUNTING_CATEGORIES)


def is_valid_category_for_module(module: str, category: str) -> bool:
    """Verifies if category belongs to the given module."""
    mod = module.lower()
    cat = category.lower()
    valid_keys = {k for k, _ in MODULE_CATEGORIES_MAP.get(mod, [])}
    # Allow generic 'other' across modules
    if cat == "other" or cat == f"{mod}_other":
        return True
    return cat in valid_keys


def normalize_category_for_module(module: str, category: str) -> str:
    """Normalizes category aliases (e.g. 'tax_other' -> 'tax_other' or 'other')."""
    cat = category.lower().strip()
    mod = module.lower().strip()
    if mod == "taxation" and cat == "other":
        return "tax_other"
    if mod == "audit" and cat == "other":
        return "audit_other"
    return cat
