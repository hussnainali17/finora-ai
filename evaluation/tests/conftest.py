"""
conftest.py — Shared pytest fixtures for Finora CA Firm evaluation suite.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Path setup — make sure the backend is importable
# ---------------------------------------------------------------------------
EVAL_ROOT = Path(__file__).resolve().parent.parent  # Finora/evaluation
REPO_ROOT = EVAL_ROOT.parent                        # Finora/
BACKEND_ROOT = REPO_ROOT / "ca-firm-system" / "backend"
DATASETS_ROOT = EVAL_ROOT / "datasets"

# Insert backend into sys.path so we can import app.*
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


# ---------------------------------------------------------------------------
# Dataset loader helpers
# ---------------------------------------------------------------------------

def load_dataset(relative_path: str) -> dict:
    """Load a JSON evaluation dataset by its path relative to datasets/."""
    path = DATASETS_ROOT / relative_path
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def datasets_root() -> Path:
    return DATASETS_ROOT


@pytest.fixture(scope="session")
def tb_clean():
    return load_dataset("trial_balance/usat_trial_balance_clean.json")


@pytest.fixture(scope="session")
def tb_with_errors():
    return load_dataset("trial_balance/usat_trial_balance_with_errors.json")


@pytest.fixture(scope="session")
def gl_clean():
    return load_dataset("general_ledger/usat_gl_clean.json")


@pytest.fixture(scope="session")
def gl_with_errors():
    return load_dataset("general_ledger/usat_gl_with_errors.json")


@pytest.fixture(scope="session")
def far_clean():
    return load_dataset("fixed_assets/usat_far_clean.json")


@pytest.fixture(scope="session")
def far_with_errors():
    return load_dataset("fixed_assets/usat_far_with_errors.json")


@pytest.fixture(scope="session")
def bank_statement_clean():
    return load_dataset("bank_cash/usat_bank_statement_clean.json")


@pytest.fixture(scope="session")
def ar_ageing():
    return load_dataset("sales_receivables/usat_ar_ageing.json")


@pytest.fixture(scope="session")
def ap_dataset():
    return load_dataset("purchases_payables/usat_ap_dataset.json")
