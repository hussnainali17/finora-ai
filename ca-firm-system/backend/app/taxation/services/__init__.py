"""Deterministic calculation services for Pakistan Taxation."""

from app.taxation.services.income_tax import compute_pakistan_income_tax
from app.taxation.services.sales_tax import compute_sales_tax

__all__ = [
    "compute_pakistan_income_tax",
    "compute_sales_tax",
]
