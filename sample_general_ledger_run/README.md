# Finora Accounting Review Pipeline: General Ledger Run Guide

This guide is prepared from a **Chartered Accountant (CA) & Audit Assurance** perspective for testing and running the Finora automated audit pipeline using the generated General Ledger dataset: `General_Ledger_October_2025.xlsx`.

---

## 1. File Overview & CA Context

### Background & Dataset Lineage
* **Client Entity:** U.S. Apparel & Textile (Pvt) Limited (`USAT`) — Head Office Unit.
* **Audit Period:** 01 October 2025 – 31 October 2025 (Interim Special Purpose Audit).
* **Currency:** Pakistani Rupee (`PKR`).
* **Source Lineage:** Extracted directly from `DATA/USAT Trial Oct-25 (A) (1).xlsx` (Sheet: `Trial Unit Wise `) and cross-referenced with `DATA/Consolidated FAR Oct-25 V5.xlsx`.
* **Nature of File:** General Ledger (GL) Transaction Extract (`23` curated transactional lines covering capital expenditures, depreciation, banking transfers, vendor settlements, stores, utility accruals, and overheads).

### Column Schema & Financial Casting Check

| Column Name | Data Type | Role in Pipeline | Audit Significance |
| :--- | :--- | :--- | :--- |
| **Date** | `YYYY-MM-DD` | `date` | Enables period cut-off testing (ISA 500 / ISA 240). |
| **Account Code** | Numeric (8-digit) | `account_code` | Precise mapping to Trial Balance Chart of Accounts (COA). |
| **Account Name** | String | `account_name` | Audit classification and grouping level. |
| **Voucher Ref** | String | `reference` | Full audit trail tracing to source vouchers (VR/JV/BP/PV). |
| **Description** | String | `description` | Transaction narration for substantive analytical testing. |
| **Debit (PKR)** | Decimal (2 dp) | `debit` | Inflow / asset acquisition / expense debit. |
| **Credit (PKR)** | Decimal (2 dp) | `credit` | Outflow / liability recognition / depreciation credit. |
| **Balance (PKR)** | Decimal (2 dp) | `balance` | Running cumulative ledger position. |

* **Total Debits:** `PKR 402,200,382.00`
* **Total Credits:** `PKR 246,226,523.00`
* **Net Movement:** `PKR 155,973,859.00` (Reconciled with the net movement across active accounts in the October 2025 Trial Balance).

---

## 2. Ingestion Settings & Upload Configuration

When uploading `General_Ledger_October_2025.xlsx` to the Finora platform:

### A. Document Upload Category
* **Upload Category Selection:** **`General Ledger (GL)`** (`general_ledger`)
* *Why this setting matters:* In the Finora backend intake classifier (`app/agents/intake_agent/classify.py`), choosing `general_ledger` provides the required category hint. This ensures the deterministic parser assigns column roles (`date`, `account_code`, `account_name`, `debit`, `credit`, `reference`, `description`) with **95% confidence**, bypassing fallback heuristic ambiguity.

### B. Client & Accounting Period Settings
1. **Client Workspace:** Select or create client: `U.S. Apparel & Textile (Pvt) Limited` (Status: `Active`).
2. **Accounting Period:** Select or define period:
   * **Period Start Date:** `2025-10-01`
   * **Period End Date:** `2025-10-31`
   * **Period Status:** `Open` *(Note: uploads are disabled if the period is locked or closed)*.
3. **Date Format Convention:** `YYYY-MM-DD` (ISO 8601).
4. **Tolerance Level:** `0.01` (Finora default threshold for rounding differences).

---

## 3. How to Run the Accounting Pipeline

The Finora pipeline operates across multi-agent stages (Agent 1: Intake & Structuring $\rightarrow$ Agent 2: Accounting Review & Reconciliation $\rightarrow$ Agent 3: Adjustments $\rightarrow$ Agent 4: Adjusted Trial Balance & Reporting).

### Step 1: Upload the Document
1. Navigate to the **Documents** section: `http://localhost:5173/clients/:clientId/periods/:periodId/documents`.
2. Under **Upload a file**:
   * Set **Category** dropdown to: **`General Ledger (GL)`**.
   * Click **Choose File** and select `General_Ledger_October_2025.xlsx`.
   * Click **Upload**.
3. **What happens under the hood:**
   * The backend FastAPI endpoint (`/clients/{client_id}/periods/{period_id}/documents/upload`) hashes the file (SHA-256), writes it to storage, and queues it for extraction.
   * **Agent 1 (Intake Engine)** detects the table layout, extracts header roles, parses numerical decimal cells without float rounding errors, and saves rows into `extracted_tables` and `extracted_rows`.

### Step 2: Trigger Accounting Review (Agent 2)
1. In the sidebar or top navigation, click **Accounting Review** (`/clients/:clientId/periods/:periodId/review`).
2. Click the **Run Accounting Review** (or **Trigger Review**) button.
3. The platform dispatches an `accounting-review-requested` event via Kafka or local async execution:
   * **General Ledger Reconciliation Module** (`app/accounting/reconciliation/general_ledger.py`) activates.
   * Aggregates transactions per account.
   * Compares GL net balances with Trial Balance balances (if TB is uploaded for the period).
   * Executes deterministic checks for duplicates, cut-off violations, and out-of-pattern statistical outliers.

### Step 3: Run via Backend API / CLI (Alternative Developer Mode)
If running directly from terminal or automated test scripts:
```powershell
# From the backend directory
cd ca-firm-system\backend

# Using Python CLI or test suite
pytest tests/ -k "reconciliation or review"

# Or calling the review agent programmatically via Python script
python -c "
import asyncio, uuid
from app.db.session import async_session_factory
from app.agents.accounting_review_agent.agent import AccountingReviewAgent

async def run():
    async with async_session_factory() as session:
        agent = AccountingReviewAgent()
        result = await agent.run_review(
            session=session,
            review_run_id=uuid.uuid4(),
            client_id=uuid.UUID('<CLIENT_UUID>'),
            period_id=uuid.UUID('<PERIOD_UUID>'),
            firm_id=uuid.UUID('<FIRM_UUID>')
        )
        print('Run summary:', result)

asyncio.run(run())
"
```

---

## 4. Expected Results & Generated Output Files

Upon completion of the review pipeline, the system produces structured database records, review schedules, and exportable findings:

### A. Generated Reconciliation Schedules (`ReconciliationSchedule`)
1. **`gl_account_summary` (General Ledger Account-Level Summary):**
   * Groups transactions by `account_code`.
   * Calculates total Debits, total Credits, net account movement, transaction count, and balance indicator.
   * Provides complete source traceability (`document_id`, `table_id`, `row_index`).
2. **`gl_tb_reconciliation` (GL $\leftrightarrow$ Trial Balance Reconciliation):**
   * Produced when a Trial Balance (`trial_balance`) is present in the period.
   * Cross-checks each GL account movement against the TB net debit/credit.
   * Highlights status: `matched`, `discrepancy`, `gl_only`, or `tb_only`.

### B. Audit Findings & Quality Checks (`ReviewFinding`)
The deterministic CA logic evaluates every row and produces audit flags if discrepancies exist:
* **Duplicate Transaction Detection (`gl_duplicate_transaction`):** Flags identical date, description, and debit/credit amounts. *(Our dataset is unique, expected finding count: `0`)*.
* **Period Cut-off Violations (`gl_out_of_period`):** Verifies all dates are between `2025-10-01` and `2025-10-31`. *(All entries strictly within October 2025, expected: `0`)*.
* **Missing Mandatory Fields (`gl_missing_field`):** Checks for presence of Date, Description, and Debit/Credit amount. *(All fields populated, expected: `0`)*.
* **Statistical Outlier / Large Transaction Flagging (`gl_large_transaction`):** Flags transactions $> \text{Mean} + 2\sigma$ per account. *(e.g., Fleet transfer of PKR 151,595,454 in Vehicles account correctly flags for CA senior review & authorization check)*.

### C. Review Run Summary & Downstream Workflows
* **Status:** Updates to `completed`.
* **Module Summary:** Shows `{ "status": "completed", "total_findings": N, "gl_rows": 23, "accounts": 8 }`.
* **Downstream Workflow:** Findings feed directly into **Agent 3 (Adjustments Agent)** for proposed journal voucher adjustments, and **Agent 4 (Reporting Agent)** for the finalized Adjusted Trial Balance and Financial Statement Lead Schedules.
