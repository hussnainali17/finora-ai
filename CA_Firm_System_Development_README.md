# CA Firm System --- Development Roadmap & AI Build Prompts

> **Purpose:** Build an AI-assisted accounting review and financial
> reporting platform for a CA firm.
>
> **Core boundary:** The client already maintains its accounting books
> and supplies Excel/CSV/PDF records. This application imports, reviews,
> reconciles and reports on those records. It must **not** create or
> maintain a bookkeeping ledger, post transactions, or replace the
> client's accounting software.

------------------------------------------------------------------------

## 1. Product scope and non-negotiable decisions

### In scope

-   Multi-client and multi-period workspace.
-   Secure upload and storage of client-provided Excel, CSV, PDF and
    supporting documents.
-   Extraction, structuring, validation and source traceability.
-   Accounting review and reconciliation.
-   Proposed period-end adjustments, kept separate until CA approval.
-   Adjusted Trial Balance as a reporting output.
-   Financial statements, supporting schedules and validation reports.
-   Four AI agents coordinated by LangGraph.
-   LiteLLM Proxy as the single LLM gateway, allowing authorized users
    to select approved models.
-   Kafka for asynchronous events and background processing.
-   CA review, approval, rejection and audit trail.

### Explicitly out of scope

-   General Ledger creation or maintenance.
-   Journal posting or transaction posting.
-   Bookkeeping functionality.
-   Tax computation, tax filing or tax agent.
-   Audit execution or audit opinion workflows.
-   Automatically approving professional accounting judgments.
-   Automatically inventing balancing entries where the client's Trial
    Balance is incorrect.

### Four AI agents only

1.  **Data Intake & Structuring Agent** --- interprets and structures
    source files.
2.  **Accounting Review & Reconciliation Agent** --- reviews
    sales/receivables, purchases/payables, bank/cash, inventory, fixed
    assets and payroll.
3.  **Period-End Adjustments Agent** --- proposes and calculates
    adjustments with evidence and rationale.
4.  **Financial Reporting & Validation Agent** --- prepares reporting
    outputs from the original Trial Balance plus CA-approved
    adjustments.

Use deterministic Python services for arithmetic, reconciliations,
depreciation calculations, adjustment application and validations. Do
not create extra agents for deterministic tasks.

------------------------------------------------------------------------

## 2. Target technology architecture

  -----------------------------------------------------------------------
  Layer                               Selected technology
  ----------------------------------- -----------------------------------
  Frontend                            React.js + TypeScript

  UI components                       Material UI (MUI)

  Backend API                         Python + FastAPI

  Agent workflow                      LangGraph

  LLM gateway                         LiteLLM Proxy

  AI providers                        Any providers/models supported and
                                      configured in LiteLLM

  Main database                       PostgreSQL

  Vector search                       pgvector, only where semantic
                                      document retrieval is needed

  Object/file storage                 MinIO in development; S3-compatible
                                      storage in production

  Event streaming                     Apache Kafka (KRaft mode)

  Background workers                  Python Kafka consumers

  Cache / short-lived coordination    Redis

  Authentication                      Keycloak or a secure JWT/OIDC
                                      implementation

  Excel processing                    Pandas + OpenPyXL

  PDF processing                      PyMuPDF; OCRmyPDF + Tesseract for
                                      scanned PDFs

  Reports                             ReportLab + OpenPyXL

  Containers                          Docker + Docker Compose

  Reverse proxy                       Nginx

  Monitoring                          Prometheus + Grafana; structured
                                      application logs
  -----------------------------------------------------------------------

### Architecture principles

-   Start as a **modular monolith** for FastAPI, plus separately
    scalable worker containers. Do not prematurely split every module
    into a microservice.
-   React calls FastAPI; the browser never calls LiteLLM directly.
-   FastAPI/LangGraph calls LiteLLM Proxy for model inference.
-   Provider API keys are held only in server-side secret
    storage/environment configuration. Never expose them to React or
    store raw keys in ordinary application tables.
-   Kafka transports durable asynchronous events and work requests.
    LangGraph remains responsible for agent workflow state, sequencing,
    branching and checkpoints.
-   PostgreSQL stores application/workflow data, not a ledger.
-   MinIO/S3 stores original files and generated artifacts. Store file
    metadata and object keys in PostgreSQL.
-   Every extracted value and review finding should be traceable to its
    source file and location where possible.
-   Keep original uploaded files immutable. Store normalized/extracted
    copies separately.
-   All money calculations use decimal arithmetic, explicit currency and
    rounding rules. Do not use binary floating-point for financial
    amounts.
-   Every adjustment has a draft/proposed/approved/rejected status and a
    complete history.
-   Only CA-approved adjustments can feed the Adjusted Trial Balance.
-   Use tenant/client-level authorization on every API, query,
    object-storage operation and background task.

------------------------------------------------------------------------

## 3. Development sequence and task breakdown

Build in the sequence below. Complete and test each phase before moving
on. Do not ask the AI coding assistant to build the entire product in
one prompt.

### Phase 0 --- Repository foundation and engineering standards

**Tasks** - Create repository structure for frontend, backend, workers,
infrastructure and documentation. - Add Docker Compose for local
development. - Add environment variable templates and secrets policy. -
Configure linting, formatting, type checking and automated tests. - Add
health-check endpoints and structured logging. - Document local setup
and architecture decisions.

**AI development prompt**

``` text
Act as a senior software architect and full-stack engineer. Set up the foundation of a CA Firm System using:
- React + TypeScript + Material UI frontend
- Python + FastAPI backend
- PostgreSQL
- Redis
- Apache Kafka in KRaft mode
- MinIO object storage
- LiteLLM Proxy
- Docker Compose

Create a clean monorepo with separate frontend, backend, worker and infrastructure directories. Use modular architecture, typed configuration, environment variables, structured logs, health checks, linting, formatting and test configuration.

Do not implement accounting features yet. Do not create a ledger or bookkeeping module. Provide:
1. Repository tree
2. Docker Compose and Dockerfiles
3. .env.example files with placeholders only
4. Backend and frontend starter applications
5. Health checks for dependencies
6. README instructions for local setup

Do not hardcode credentials. Do not expose secrets to the frontend. Explain each major setup decision and run available checks.
```

**Acceptance criteria** - A developer can start the infrastructure and
applications using documented commands. - No secrets are committed. -
Frontend and backend health checks work. - Automated test commands are
documented.

------------------------------------------------------------------------

### Phase 1 --- Database design, authentication and tenant isolation

**Tasks** - Design PostgreSQL schema and migrations. - Implement users,
roles, organizations/firm, clients and accounting periods. - Implement
login/session handling with OIDC/Keycloak or secure JWT. - Add
role-based and client-level access control. - Add audit events for
sensitive actions.

**Suggested roles** - Firm Admin - CA / Reviewer - Accountant / Staff -
Read-only Client User (only if client portal access is required)

**AI development prompt**

``` text
Implement the identity, authorization and initial database layer for the CA Firm System.

Stack: FastAPI, SQLAlchemy 2, Alembic, PostgreSQL, React + TypeScript.

Create entities for:
- Firm/organization
- User
- Role and permissions
- Client
- Accounting period
- User-to-firm and user-to-client access assignments
- Audit event

Requirements:
- Enforce tenant and client isolation in backend services and database queries.
- Implement secure authentication using the configured OIDC provider or a secure JWT integration.
- Implement role-based permissions. A user must only access clients and periods they are authorized for.
- Record actor, action, target, timestamp and relevant metadata for sensitive operations.
- Use migrations, validation schemas and automated tests.
- Never put secrets or provider API keys in frontend code.
- Do not create ledger, journal-posting or bookkeeping tables.

First present the schema and authorization design, then implement it. Include tests proving that one client cannot access another client's records.
```

**Acceptance criteria** - Users can sign in and sign out. - Unauthorized
client access is denied by the backend. - Database migrations run from a
clean database. - Cross-client access tests pass.

------------------------------------------------------------------------

### Phase 2 --- Client workspace and file management

**Tasks** - Create client and accounting-period screens. - Implement
file upload to MinIO/S3. - Support Excel, CSV and PDF, with configurable
size/type limits. - Store immutable original files and metadata. - Add
file listing, download authorization and upload status. - Calculate file
hash for duplicate detection. - Publish a `file.uploaded` event to Kafka
after the object and metadata are safely stored.

**AI development prompt**

``` text
Build the client workspace and secure document management module.

Frontend: React + TypeScript + MUI.
Backend: FastAPI.
Storage: MinIO/S3.
Database: PostgreSQL.
Events: Kafka.

Features:
- Client list, client detail and accounting-period selection.
- Upload Excel, CSV and PDF files to a selected client and accounting period.
- Accept supporting documents such as bank statements, invoices, receipts, contracts, fixed asset schedules, inventory reports and payroll schedules.
- Store original files unchanged in object storage.
- Store metadata in PostgreSQL: client, period, original filename, object key, MIME type, size, SHA-256 hash, uploader, timestamp and processing status.
- Enforce client-level authorization on upload, listing, download and deletion/retention operations.
- Detect duplicate uploads using hashes and provide a safe user-facing result.
- Publish a Kafka event only after file storage and metadata persistence succeed. Design for safe retries and duplicate event delivery.
- Show upload and processing status in React.

Do not parse accounting contents in this phase. Do not create a ledger. Add API, UI and integration tests.
```

**Acceptance criteria** - Files are stored outside the database. -
Original files remain unchanged. - Unauthorized users cannot access file
objects. - Upload event is not published for failed uploads.

------------------------------------------------------------------------

### Phase 3 --- Data extraction and structuring (Agent 1)

**Tasks** - Build Excel workbook/sheet inspection and CSV parsing. -
Extract text and tables from digital PDFs. - Add OCR fallback for
scanned PDFs. - Identify reporting period, sheet headers, columns and
likely accounting data type. - Normalize dates, descriptions, currencies
and amounts without losing original values. - Preserve source
traceability: file ID, sheet/page, row and cell references where
possible. - Add data-quality findings and human correction screen. - Use
LLM for interpretation/classification, not arithmetic.

**AI development prompt**

``` text
Implement Agent 1: Data Intake & Structuring for the CA Firm System.

The client supplies its own accounting exports and documents. This product must not create or maintain a ledger.

Input formats:
- Excel workbooks and sheets
- CSV files
- Digital PDFs
- Scanned PDFs and images

Use Pandas/OpenPyXL for spreadsheets, PyMuPDF for digital PDF extraction, and OCRmyPDF/Tesseract as an OCR path for scanned PDFs.

Agent responsibilities:
1. Inspect workbook sheets, dimensions, merged cells, headers and likely table ranges.
2. Identify likely document type, accounting period, currency and column meanings.
3. Extract rows and document text.
4. Normalize formats while retaining the exact original source and raw values.
5. Suggest account/column mappings using the configured LLM through LiteLLM.
6. Flag missing headers, ambiguous dates, invalid amounts, duplicate rows and unreadable sections.
7. Preserve source references: file ID, sheet name, row number, column/cell and PDF page/bounding region where available.
8. Save extracted/normalized data and quality findings as review data, not ledger postings.
9. Provide a React screen for staff to inspect and correct uncertain mappings.

Use deterministic parsers first and LLM assistance only where interpretation is needed. Never let the LLM invent missing values. Do not calculate or post journal entries. Add representative fixtures and tests for messy workbooks, multiple sheets, blank rows, different date formats, PDFs and OCR failures.
```

**Acceptance criteria** - Extraction output is reproducible and
traceable to source. - Ambiguous or missing values are flagged, not
guessed. - Original values are preserved alongside normalized values. -
Staff can review and correct uncertain mappings.

------------------------------------------------------------------------

### Phase 4 --- LiteLLM gateway and model selection

**Tasks** - Deploy LiteLLM Proxy. - Configure approved model aliases and
provider credentials server-side. - Create backend model-configuration
API. - Add model selector to authorized settings screen. - Assign
defaults by agent and optional per-task overrides. - Log model/provider,
latency, token usage, cost metadata if available, and request
correlation ID. - Configure timeouts, retry limits and fallback
policy. - Prevent arbitrary model access unless explicitly allowed by
firm administrators.

**AI development prompt**

``` text
Implement centralized LLM access through LiteLLM Proxy.

Requirements:
- All backend AI calls must go through LiteLLM Proxy. No agent may call provider SDKs directly.
- Configure model aliases in LiteLLM. Provider credentials must remain server-side in environment variables or a secrets manager.
- Create a backend model registry/configuration API exposing only approved model aliases and display metadata.
- Build a React settings screen where authorized administrators can enable/disable approved models and set default models for each of the four agents.
- Permit authorized users to choose an approved model for a workflow or task when policy allows.
- Persist model alias and configuration version, not raw API keys, in application data.
- Log model alias, provider, request ID, agent, task, latency, token usage and available cost metadata.
- Add timeouts, bounded retries, error handling and explicitly configured fallback behavior.
- Never expose LiteLLM master keys or provider API keys to the browser.
- Add tests for unauthorized model selection, unavailable models, provider failures and fallback behavior.

Do not assume every model supports identical context length, tools, structured output or vision. Validate model capabilities before assigning a model to a task.
```

**Acceptance criteria** - Agents call only the LiteLLM gateway. -
Browser responses contain no provider secrets. - Authorized users can
switch between approved models. - Model use is logged and failures are
handled safely.

------------------------------------------------------------------------

### Phase 5 --- Kafka event infrastructure and worker framework

**Tasks** - Configure Kafka topics, partitions, retention and consumer
groups. - Define versioned event schemas. - Implement producer and
consumer utilities. - Add idempotency, retries, dead-letter topics and
observability. - Implement worker health checks and graceful shutdown. -
Ensure database state and event publication are reliable (use an outbox
pattern where appropriate).

**Suggested topics** - `file-uploaded` - `file-processing` -
`data-structured` - `accounting-review-requested` -
`reconciliation-requested` - `adjustment-calculation-requested` -
`ca-approval-events` - `report-generation-requested` -
`workflow-status` - Dead-letter topics for failed event types

**AI development prompt**

``` text
Build the Kafka event and background worker foundation.

Use Apache Kafka in KRaft mode and Python consumers. FastAPI is the API layer; LangGraph remains the workflow orchestrator.

Implement:
- Versioned event schemas with event_id, event_type, schema_version, tenant_id, client_id, accounting_period_id, correlation_id, occurred_at and payload.
- Producers and consumers with explicit serialization and validation.
- Consumer groups for file processing, accounting calculations and report generation.
- Idempotent processing using event_id and durable job state.
- Bounded retries with backoff and dead-letter handling.
- Graceful worker shutdown and health/readiness endpoints.
- Structured logs and metrics.
- Outbox pattern or equivalent reliable event publication so database changes and events cannot silently diverge.
- Authorization/context validation for every event.
- Tests for duplicate delivery, retries, malformed events, worker restart and dead-letter routing.

Do not put sensitive document contents or API keys in Kafka messages. Use file IDs/object keys and authorized backend retrieval instead. Do not use Kafka to replace LangGraph checkpoints or workflow state.
```

**Acceptance criteria** - Duplicate events do not duplicate business
effects. - Failed jobs are observable and recoverable. - Workers can
restart without losing durable work. - Events carry tenant/client
context but not secrets or full sensitive documents.

------------------------------------------------------------------------

### Phase 6 --- Accounting review and reconciliation (Agent 2)

**Tasks** - Create review modules for sales/receivables,
purchases/payables, bank/cash, inventory, fixed assets and payroll. -
Implement deterministic reconciliation and validation services. - Use
LLM for classification assistance, explanations and review-note
drafts. - Store findings, evidence references, exceptions and reviewer
status. - Build review dashboards and schedules.

**AI development prompt**

``` text
Implement Agent 2: Accounting Review & Reconciliation.

This agent reviews client-provided accounting records and supporting evidence. It does not create a ledger, post transactions or silently alter source data.

Build these review modules inside this one agent:
1. Sales and receivables
2. Purchases and payables
3. Bank and cash
4. Inventory
5. Fixed assets
6. Payroll accounting

For each module:
- Identify required source datasets and supporting evidence.
- Run deterministic checks and reconciliations in Python.
- Flag missing, duplicated, inconsistent, aged or unusual records.
- Preserve references to source file, sheet, row or PDF page.
- Store reconciliation results, exceptions, evidence links and review status.
- Allow staff to mark findings as open, explained, resolved or escalated.
- Use LiteLLM for ambiguous classification suggestions and plain-language explanations only.
- Do not let an LLM perform authoritative arithmetic or invent evidence.
- Do not automatically resolve a discrepancy without recorded evidence and reviewer action.

Create reusable accounting calculation functions with Decimal arithmetic, currency awareness and explicit tolerances. Provide unit tests using realistic sample datasets. Build React review screens with filters, evidence drill-down and status updates.

Do not add tax or audit functionality. Do not create separate AI agents for each accounting module.
```

**Acceptance criteria** - Each review result links to source evidence. -
Calculations are deterministic and tested. - Exceptions remain visible
until resolved or accepted by an authorized reviewer. - No source record
is overwritten.

------------------------------------------------------------------------

### Phase 7 --- Period-end adjustments (Agent 3)

**Tasks** - Identify potential accruals, prepayments, depreciation and
other configured accounting adjustments. - Calculate using deterministic
services. - Create proposed adjustment register with debit/credit
accounts, amount, currency, rationale, formula and evidence. - Implement
draft, proposed, approved and rejected states. - Add CA
approval/rejection and comments. - Keep adjustments separate from client
source records.

**AI development prompt**

``` text
Implement Agent 3: Period-End Adjustments.

The agent identifies and proposes adjustments; it must never post journals to a ledger.

Support configurable adjustment categories such as:
- Accruals
- Prepayments
- Depreciation
- Other supported period-end adjustments approved for the product scope

For each proposed adjustment store:
- Unique adjustment ID
- Client and accounting period
- Debit account mapping
- Credit account mapping
- Amount and currency
- Calculation details and assumptions
- Accounting rationale
- Supporting evidence/source references
- Prepared-by agent/task
- Status and status history
- CA reviewer, decision, timestamp and comments

Use deterministic Python calculation functions with Decimal arithmetic. The LLM may explain evidence or draft a rationale, but must not be the authoritative calculator or approver.

Implement CA approval controls:
- Proposed adjustments require explicit authorized approval.
- Rejected adjustments cannot feed reporting.
- Changes after approval must invalidate the prior approval and create a new version.
- Preserve full history.
- Do not write to client ledgers or source files.

Build React screens for reviewing, editing, approving and rejecting proposed adjustments. Add tests proving that only currently approved adjustments are eligible for the Adjusted Trial Balance.
```

**Acceptance criteria** - No adjustment is applied before CA approval. -
Approval history is immutable/auditable. - Revisions require renewed
approval. - No ledger posting endpoint or functionality exists.

------------------------------------------------------------------------

### Phase 8 --- Adjusted Trial Balance, reporting and validation (Agent 4)

**Tasks** - Import/use the client's original Trial Balance. - Validate
original TB without modifying it. - Apply only approved adjustments in a
separate reporting calculation. - Generate Adjusted Trial Balance. -
Generate financial statements and supporting schedules. - Validate
arithmetic, mapping completeness and statement consistency. - Flag
unsupported or missing information.

**AI development prompt**

``` text
Implement Agent 4: Financial Reporting & Validation.

Inputs:
- Original client-provided Trial Balance
- Approved adjustment register only
- Account mappings
- Relevant accounting review schedules and supporting data

Rules:
- Never alter the original Trial Balance.
- Never include draft, proposed or rejected adjustments.
- Calculate the Adjusted Trial Balance as a separate reporting output from the original TB plus approved adjustments.
- If the original TB is unbalanced or incomplete, flag the issue. Never invent a balancing entry.
- Use deterministic Python services and Decimal arithmetic for all financial calculations.
- Use the LLM only for explanations, narrative drafting and presentation assistance.

Outputs as applicable and supported by data:
- Adjusted Trial Balance
- Statement of Profit or Loss
- Statement of Financial Position
- Statement of Cash Flows
- Statement of Changes in Equity
- Sales/receivables and purchases/payables ageing
- Bank reconciliation
- Inventory review schedule
- Fixed asset and depreciation schedules
- PPE movement statement
- Payroll accounting review schedule
- Validation and unresolved-exception report

Implement configurable account-to-statement mapping, reporting-period handling, comparative columns where supplied, rounding policy and report versioning. Clearly flag missing inputs and unsupported statements rather than fabricating amounts.

Generate PDF and Excel reports. Provide preview, download and CA sign-off screens. Add tests for balanced/unbalanced TBs, approved/unapproved adjustments, statement totals, rounding and missing mappings.
```

**Acceptance criteria** - Adjusted TB includes approved adjustments
only. - Original TB is preserved. - Reports reconcile to the Adjusted TB
according to defined mappings. - Missing data and validation failures
are explicit.

------------------------------------------------------------------------

### Phase 9 --- LangGraph end-to-end orchestration

**Tasks** - Define typed workflow state and checkpoints. - Connect the
four agents in the correct sequence. - Add conditional routing for
missing data and review exceptions. - Pause for CA approval. - Resume
after approval/rejection. - Add retries, timeouts and recovery. -
Correlate workflow state with Kafka jobs and UI status.

**AI development prompt**

``` text
Integrate the four implemented agents using LangGraph.

Workflow:
1. Client uploads files.
2. Agent 1 extracts and structures records.
3. Data quality gate: if essential data is missing or ambiguous, route to staff correction.
4. Agent 2 performs accounting review and reconciliation.
5. Agent 3 proposes period-end adjustments.
6. Workflow pauses for CA review and approval.
7. Agent 4 uses the original Trial Balance and approved adjustments to prepare reporting outputs.
8. Validation gate identifies unresolved issues.
9. Authorized CA performs final review and sign-off.
10. Reports become available to authorized users.

Requirements:
- Use typed, versioned workflow state.
- Persist checkpoints so workflows survive process restarts.
- Implement human-in-the-loop pause/resume for CA approval.
- Maintain client, period, workflow and correlation IDs.
- Route failures to recoverable states; do not silently skip failed steps.
- Use Kafka for asynchronous task dispatch and event notifications, not as the workflow state engine.
- Prevent duplicate execution from duplicate Kafka events.
- Record agent inputs/outputs, model alias, timing, errors and evidence references without logging secrets or unnecessary sensitive content.
- Add end-to-end tests for success, missing data, rejected adjustments, worker restart, retry and final report generation.

Do not add agents beyond the four defined in this README.
```

**Acceptance criteria** - Full workflow can pause and resume. - No
reporting stage runs with unapproved adjustments. - Failed steps can be
retried without duplicating outputs. - User sees meaningful workflow
status.

------------------------------------------------------------------------

### Phase 10 --- Frontend completion and user experience

**Tasks** - Dashboard and client workspace. - Accounting period workflow
board. - Upload and extraction review screens. - Reconciliation and
exception screens. - Adjustment approval screens. - Model settings
screen. - Report preview/download and sign-off. - Notifications and
activity history.

**AI development prompt**

``` text
Complete the React + TypeScript + Material UI application for the CA Firm System.

Build responsive, accessible screens for:
- Login and user profile
- Firm dashboard
- Client list and client workspace
- Accounting periods
- File upload and processing status
- Extracted data review and mapping corrections
- Accounting review modules and reconciliation schedules
- Exceptions and supporting evidence
- Proposed adjustments and CA approval
- Adjusted Trial Balance preview
- Financial statements and report downloads
- Workflow activity and audit history
- Approved AI model selection/settings for authorized users

Use the FastAPI backend contracts. Do not put accounting calculations or authorization decisions in the browser. The backend is authoritative.

Use typed API clients, loading/error/empty states, pagination, filters and accessible forms. Use WebSocket or polling for workflow status as appropriate. Enforce UI permissions for usability, while relying on backend authorization for security.

Do not create ledger, journal posting, tax or audit screens. Do not expose provider API keys or LiteLLM secrets.
```

**Acceptance criteria** - Screens reflect backend workflow state. - All
sensitive actions are permission-checked by the backend. - Errors and
incomplete workflows are clearly shown. - No out-of-scope modules
appear.

------------------------------------------------------------------------

### Phase 11 --- Security, quality assurance and deployment

**Tasks** - Threat model and access-control review. - File validation,
malware scanning integration point and safe download handling. -
Encryption in transit and at rest. - Secret management and key
rotation. - Backup/restore and disaster recovery. - Load, integration
and end-to-end tests. - Monitoring, alerting and deployment pipeline. -
Production runbooks.

**AI development prompt**

``` text
Perform a production-readiness review of the CA Firm System.

Review the React frontend, FastAPI backend, PostgreSQL, MinIO/S3, Kafka, Redis, LangGraph, LiteLLM and worker services.

Check:
- Authentication, authorization and tenant/client isolation
- Object storage access and file upload validation
- Secret management and accidental credential exposure
- SQL injection, XSS, CSRF and API abuse risks
- Sensitive data in logs, Kafka events and LLM prompts
- Rate limits, timeouts, retries and denial-of-service protections
- Database migrations, backups and restore procedures
- Kafka durability, consumer idempotency and dead-letter handling
- LLM provider timeouts, spend controls and model allowlists
- Audit trail integrity
- Financial calculation correctness and Decimal usage
- Workflow recovery and approval-state integrity

Add automated security, integration and end-to-end tests. Provide Docker production deployment configuration, environment/secrets checklist, monitoring dashboards, backup policy and incident runbooks.

Do not claim compliance or security certification without independent evidence. Do not weaken authorization to make tests pass.
```

**Acceptance criteria** - Security and isolation tests pass. - Backup
restoration is tested. - Monitoring and alerting are configured. -
Production secrets are managed outside source control.

------------------------------------------------------------------------

## 4. Recommended repository structure

``` text
ca-firm-system/
│
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   ├── components/
│   │   ├── features/
│   │   │   ├── auth/
│   │   │   ├── clients/
│   │   │   ├── documents/
│   │   │   ├── data-review/
│   │   │   ├── accounting-review/
│   │   │   ├── adjustments/
│   │   │   ├── reporting/
│   │   │   └── model-settings/
│   │   ├── services/
│   │   ├── hooks/
│   │   └── types/
│   └── package.json
│
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── core/
│   │   ├── db/
│   │   ├── models/
│   │   ├── schemas/
│   │   ├── services/
│   │   ├── agents/
│   │   │   ├── intake_agent/
│   │   │   ├── accounting_review_agent/
│   │   │   ├── adjustments_agent/
│   │   │   └── reporting_agent/
│   │   ├── workflows/
│   │   ├── accounting/
│   │   │   ├── reconciliation/
│   │   │   ├── depreciation/
│   │   │   ├── adjustments/
│   │   │   └── validation/
│   │   └── integrations/
│   │       ├── litellm/
│   │       ├── kafka/
│   │       └── storage/
│   ├── migrations/
│   └── tests/
│
├── workers/
│   ├── consumers/
│   ├── jobs/
│   ├── event_schemas/
│   └── tests/
│
├── infrastructure/
│   ├── docker/
│   ├── kafka/
│   ├── litellm/
│   ├── nginx/
│   └── monitoring/
│
├── docs/
│   ├── architecture.md
│   ├── database-design.md
│   ├── api-contracts.md
│   ├── event-contracts.md
│   ├── accounting-rules.md
│   └── security.md
│
├── .env.example
├── docker-compose.yml
└── README.md
```

This is a suggested structure; adjust it to the actual framework
conventions while preserving the separation of concerns.

------------------------------------------------------------------------

## 5. Shared instructions to prepend to every AI coding prompt

Use this block before giving any phase prompt to your coding assistant:

``` text
PROJECT-WIDE RULES — CA FIRM SYSTEM

1. Read the existing README, architecture documents, database schema and current code before making changes.
2. Do not rewrite working modules or change architectural decisions without explaining why and getting approval.
3. Build only the requested phase. Do not generate the entire application at once.
4. The client already has accounting books and supplies source files. Never create a ledger, bookkeeping system, journal posting or transaction posting functionality.
5. The product scope is accounting review and financial reporting only. Tax and audit modules are excluded.
6. Use exactly four AI agents: Data Intake, Accounting Review, Period-End Adjustments, Financial Reporting.
7. Use deterministic Python services for arithmetic, reconciliations, depreciation and financial validation. Never rely on an LLM for authoritative calculations.
8. All AI calls must go through LiteLLM Proxy. Never call provider APIs directly from agents or frontend code.
9. Kafka is for asynchronous events and background processing. LangGraph manages agent workflow state and sequencing.
10. Preserve original client files and original Trial Balance. Never silently modify source records.
11. Only CA-approved adjustments may be applied to the Adjusted Trial Balance.
12. Enforce tenant/client isolation on every backend operation and background job.
13. Use Decimal for money calculations and preserve currency/rounding metadata.
14. Add tests for every meaningful feature, including negative and authorization cases.
15. Do not use mock success responses as a substitute for implemented functionality. Clearly label any temporary mock or TODO.
16. Before finishing, report files changed, design decisions, commands run, test results, known limitations and next steps.
17. Update relevant documentation and API/event contracts whenever implementation changes them.
```

------------------------------------------------------------------------

## 6. Global definition of done

A phase is complete only when: - Its code is implemented and integrated
with the existing project. - Database migrations and API/event contracts
are updated where required. - Unit and integration tests are added and
pass. - Authorization and client isolation are tested. - Errors, retries
and failure states are handled. - Documentation and environment examples
are updated. - No ledger, posting, tax or audit functionality has been
introduced. - The developer provides a short implementation report and a
list of remaining limitations.

------------------------------------------------------------------------

## 7. Suggested implementation order

    Order Phase                                        Priority
  ------- -------------------------------------------- -----------
        1 Repository foundation                        Essential
        2 Database, authentication, tenant isolation   Essential
        3 Client workspace and file management         Essential
        4 Data extraction --- Agent 1                  Essential
        5 LiteLLM gateway and model selection          Essential
        6 Kafka and worker framework                   Essential
        7 Accounting review --- Agent 2                Essential
        8 Period-end adjustments --- Agent 3           Essential
        9 Reporting --- Agent 4                        Essential
       10 LangGraph end-to-end workflow                Essential
       11 Frontend completion                          Essential
       12 Security, QA and deployment                  Essential

**Practical recommendation:** Build and test one vertical slice first:
create a client → upload one Trial Balance Excel file → extract and
review it → show its source rows. Then expand to the remaining file
types and accounting modules. This reduces integration risk before the
full agent workflow is built.

------------------------------------------------------------------------

## 8. Important architecture note

Kafka adds operational complexity. It is justified when the platform
needs concurrent file processing, multiple workers, durable event
handling and independent scaling. For a small proof of concept, a
simpler worker queue may be faster; if Kafka is a firm requirement,
implement it in Phase 5 with idempotency and observability from the
start.

Likewise, pgvector is optional. Add it only when semantic retrieval
across supporting documents is actually needed; ordinary relational
queries and source references should remain the default.

**The final product is an accounting review and financial reporting
system --- not an accounting or bookkeeping package.**
