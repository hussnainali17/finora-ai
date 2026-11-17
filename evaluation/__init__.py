"""
Finora CA Firm System — DeepEval Evaluation Suite
==================================================

This package evaluates the Finora AI CA Firm System's accounting review
agents using the DeepEval framework. It tests:

1. Deterministic reconciliation checks (GL, Trial Balance, Fixed Assets, etc.)
2. LLM-based explanation quality (correctness, relevance, faithfulness)
3. Edge cases & robustness

Dataset structure:
  evaluation/datasets/
    trial_balance/     — Trial balance datasets (clean & with errors)
    general_ledger/    — General ledger datasets (clean & with errors)
    fixed_assets/      — Fixed asset register datasets (clean & with errors)
    bank_cash/         — Bank statement datasets
    sales_receivables/ — Accounts receivable / ageing datasets
    purchases_payables/— Accounts payable datasets

Run:
    cd d:/hussnain/Final-Year-Project/7th-sem-final/Finora/evaluation
    pip install deepeval
    python -m pytest tests/ -v

Or run a single test module:
    python -m pytest tests/test_general_ledger.py -v
    python -m pytest tests/test_fixed_assets.py -v
"""
