"""Taxation statutory rules and versioned rate cards."""

from app.taxation.rules.rates import (
    RULE_SET_TY2024,
    RULE_SET_TY2025,
    resolve_rule_set,
    resolve_super_tax_rate,
)

__all__ = [
    "RULE_SET_TY2024",
    "RULE_SET_TY2025",
    "resolve_rule_set",
    "resolve_super_tax_rate",
]
