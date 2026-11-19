# Finora AI CA Firm System — Evaluation Framework

This folder contains the **DeepEval-based evaluation suite** for the Finora AI CA Firm System.

## 📁 Structure

```
evaluation/
├── datasets/                        # Input datasets for evaluation
│   ├── trial_balance/
│   │   ├── usat_trial_balance_clean.json       # Clean TB from USAT Oct-25 data
│   │   └── usat_trial_balance_with_errors.json # TB with injected errors
│   ├── general_ledger/
│   │   ├── usat_gl_clean.json                  # 20-entry balanced GL
│   │   └── usat_gl_with_errors.json            # GL with 5 injected error types
│   ├── fixed_assets/
│   │   ├── usat_far_clean.json                 # Clean FAR from Consolidated FAR Oct-25
│   │   └── usat_far_with_errors.json           # FAR with 5 injected PPE errors
│   ├── bank_cash/
│   │   └── usat_bank_statement_clean.json      # Bank stmt + cash book (balanced)
│   ├── sales_receivables/
│   │   └── usat_ar_ageing.json                 # AR ageing with overdue debtors
│   └── purchases_payables/
│       └── usat_ap_dataset.json                # AP with unmatched invoices & credit notes
│
├── tests/
│   ├── conftest.py              # Shared pytest fixtures
│   ├── test_datasets.py         # Dataset structure validation (no backend needed)
│   ├── test_general_ledger.py   # GL reconciliation module tests + LLM quality
│   ├── test_fixed_assets.py     # Fixed assets (PPE) module tests + LLM quality
│   └── test_trial_balance.py    # Trial balance dataset + TB→GL reconciliation
│
├── requirements.txt
└── README.md
```

## 🚀 Quick Start

### 1. Install dependencies

```bash
cd ca-firm-system/backend
venv\Scripts\activate   # Windows
pip install -r evaluation/requirements.txt
```

### 2. Run dataset structure tests (no backend needed)

```bash
cd ca-firm-system/backend/evaluation
python -m pytest tests/test_datasets.py -v
```

This validates that all 9 JSON datasets are well-formed and contain the expected injected errors.

### 3. Run deterministic reconciliation module tests

> These require the backend to be importable (activate backend venv first).

```bash
# All tests
python -m pytest tests/ -v

# Single module
python -m pytest tests/test_general_ledger.py -v
python -m pytest tests/test_fixed_assets.py -v
python -m pytest tests/test_trial_balance.py -v
```

### 4. Run LLM explanation quality tests (requires API key)

```bash
# Set your API key first
$env:OPENAI_API_KEY = "sk-..."      # PowerShell
# or
set OPENAI_API_KEY=sk-...           # CMD

# Then run (LLM tests are auto-skipped if no key is set)
python -m pytest tests/ -v -k "LLM"
```

---

## 📊 What Each Test Validates

### `test_datasets.py` — Dataset Integrity (no backend)
| Test | What it checks |
|------|----------------|
| `test_dataset_has_metadata` | All 9 datasets have required metadata fields |
| `test_total_debits_equal_credits` | Clean GL: DR = CR = 102,900,000 PKR |
| `test_has_null_date_row` | Errors GL: at least 1 row with `date = null` |
| `test_has_out_of_period_rows` | Errors GL: at least 1 row dated before period start |
| `test_nbv_equals_cost_minus_accum_dep` | Clean FAR: NBV = Cost − AccumDep for all assets |
| `test_has_negative_nbv_in_errors` | Errors FAR: at least 1 asset with NBV < 0 |
| `test_outstanding_balance_is_amount_minus_received` | AR: outstanding = invoice − received |

### `test_general_ledger.py` — GL Reconciliation Module
| Test | Expected outcome |
|------|-----------------|
| `test_no_findings_on_clean_data` | 0 findings on 20-entry balanced GL |
| `test_gl_is_balanced_on_clean_data` | `is_balanced = True` |
| `test_missing_date_detected` | `gl_missing_field` finding for null-date row |
| `test_out_of_period_entry_detected` | `gl_out_of_period` for 2024-12-31 entries |
| `test_duplicate_transaction_detected` | `gl_duplicate_transaction` for SI-2025-100 |
| `test_total_findings_above_minimum` | ≥ 5 findings on corrupted GL |
| `test_gl_vs_tb_reconciliation_matched` | 0 discrepancies when GL = TB |

### `test_fixed_assets.py` — PPE / FAR Module
| Test | Expected outcome |
|------|-----------------|
| `test_no_critical_findings_on_clean_data` | 0 error-severity findings on clean FAR |
| `test_missing_acquisition_date_detected` | Finding for ERR-001 (null date) |
| `test_negative_nbv_detected` | Finding for ERR-002 (Generator, NBV = −350K) |
| `test_fully_deprecated_active_detected` | Finding for ERR-003 (Sewing Machine) |
| `test_disposal_without_proceeds_detected` | Finding for ERR-004 (Forklift disposal) |
| `test_total_findings_above_minimum` | ≥ 4 findings on corrupted FAR |

---

## 📦 Data Sources

| Dataset | Source file |
|---------|------------|
| Trial Balance | `DATA/USAT Trial Oct-25 (A) (1).xlsx` — "Trial Unit Wise" sheet |
| Fixed Assets (clean) | `DATA/Consolidated FAR Oct-25 V5.xlsx` — "FAR Consolidated" sheet |
| Fixed Assets (errors) | Derived from above, with 5 injected PPE errors |
| General Ledger | Synthetic entries consistent with USAT account codes |
| Bank Statement | Synthetic, consistent with USAT HBL account structure |
| AR Ageing | Synthetic, consistent with USAT debtor account codes |
| AP Dataset | Synthetic, consistent with USAT creditor account codes (30001xxx) |

---

## 🔑 DeepEval LLM Metrics Used

| Metric | Test files | Purpose |
|--------|-----------|---------|
| `AnswerRelevancyMetric` | GL, FAR | Is the LLM explanation relevant to the finding? |
| `FaithfulnessMetric` | GL | Does the explanation faithfully represent the finding facts? |

> LLM tests are auto-skipped if no `OPENAI_API_KEY` or `GEMINI_API_KEY` is set.

---

## 📝 Adding More Datasets

To add a new evaluation dataset:
1. Create a JSON file in the appropriate `datasets/<category>/` folder
2. Include `metadata`, `rows`, and `expected_checks` keys
3. Document injected errors with `_error_injected` keys on individual rows
4. Add a corresponding test in `tests/test_<module>.py`
