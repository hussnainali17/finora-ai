# API contracts (Phase 1 - 3)

Base path `/api/v1`. JSON. Errors: `{"detail": "<message>"}` (422 validation errors use FastAPI's list
form). Authenticated routes need `Authorization: Bearer <access token>`. Interactive docs: `/docs`.

Status codes: `401` not authenticated / bad token, `403` authenticated but missing permission,
`404` not found **or outside your firm/client scope**, `409` conflict (duplicate, overlap, state),
`422` invalid input.

## Auth
| Method & path | Permission | Notes |
|---|---|---|
| `POST /auth/login` `{email, password}` | public | 200 `{access_token, token_type, expires_in, user}` + `Set-Cookie: ca_refresh`. Generic 401 for any failure. |
| `POST /auth/refresh` | refresh cookie | Rotates the cookie; returns the same body as login. 403 on untrusted `Origin`. |
| `POST /auth/logout` | refresh cookie | 204; idempotent; clears cookie; kills the session's access tokens. |
| `GET /auth/me` | any user | `{id, email, full_name, firm_id, firm_name, role, permissions[]}` |
| `POST /auth/change-password` `{current_password, new_password}` | any user | 204; revokes all sessions. |

## Users and roles (`user:read` / `user:manage`, firm-scoped)
| `GET /roles` (any user) | `GET /users?limit&offset` | `POST /users` `{email, full_name, role_key, password}` -> 201 |
|---|---|---|
| `GET /users/{id}` | `PATCH /users/{id}` `{full_name?, role_key?, is_active?}` | A firm must keep >= 1 active Firm Admin (409). Deactivating revokes sessions. |

## Clients (scope: assigned clients; Firm Admin = all in firm)
| Method & path | Permission |
|---|---|
| `GET /clients?limit&offset&status&q` | `client:read` |
| `POST /clients` `{code, name, legal_name?, base_currency, fiscal_year_end_month?, notes?}` | `client:create` (non-admin creator is auto-assigned) |
| `GET /clients/{id}` | `client:read` |
| `PATCH /clients/{id}` `{name?, legal_name?, fiscal_year_end_month?, notes?, status?}` | `client:update` (`status: archived` to archive) |
| `GET /clients/{id}/access` | `client:access_manage` |
| `POST /clients/{id}/access` `{user_id}` -> 201 (idempotent) | `client:access_manage` (user must be in the same firm and active) |
| `DELETE /clients/{id}/access/{user_id}` -> 204 | `client:access_manage` |

## Accounting periods
| Method & path | Permission |
|---|---|
| `GET /clients/{id}/periods` | `period:read` |
| `POST /clients/{id}/periods` `{label, start_date, end_date}` | `period:create` (409 on overlap / duplicate label / archived client) |
| `GET /clients/{id}/periods/{pid}` | `period:read` |
| `PATCH /clients/{id}/periods/{pid}` `{label?, start_date?, end_date?}` | `period:update` (open periods only) |
| `POST /clients/{id}/periods/{pid}/close` / `.../reopen` | `period:close` |

## Documents (Phase 2) - `/clients/{client_id}/periods/{period_id}/documents`
| Method & path | Permission | Notes |
|---|---|---|
| `POST` (multipart: `file`, `category`) | `document:upload` | 201 `DocumentOut`. Period must be open, client active. Errors: 413 too large, 415 type/content mismatch, 422 empty file/bad category, 409 closed period or **duplicate**, 503 storage unavailable. |
| `GET ?limit&offset&category&status&q` | `document:read` | Removed files are not listed. |
| `GET /{id}` | `document:read` | |
| `GET /{id}/download` | `document:read` | Streams the original through the API (no presigned/public URLs). `Content-Disposition: attachment`, `X-Content-Type-Options: nosniff`, `Cache-Control: private, no-store`, `X-Content-SHA256`. Audited. |
| `DELETE /{id}` -> 204 | `document:delete` | Soft delete; object retained; open periods only. |

Duplicate response (409):
`{"detail": "This exact file has already been uploaded to this period", "code": "duplicate_document",
"existing_document_id": "...", "existing_filename": "..."}` - only ever reveals a file inside a client the
caller can already access.

`DocumentOut`: `{id, client_id, period_id, category, original_filename, content_type, size_bytes, sha256,
status, uploaded_by, uploaded_by_email, created_at}`.

Accepted types (configurable): pdf, xlsx, xls, csv, png, jpg/jpeg. The extension must be on the allow-list
**and** the bytes must match it (PDF/PNG/JPEG/OLE signatures; xlsx must be a zip containing
`[Content_Types].xml` and `xl/`; csv must be NUL-free text). Macro-enabled workbooks (.xlsm) and other
formats are rejected. Max size `MAX_UPLOAD_BYTES` (50 MiB).

## Extraction (Phase 3) - `/clients/{client_id}/periods/{period_id}/documents/{document_id}/extraction`
The document must be live and in the caller's client scope (else 404). Extraction runs automatically after upload.
| Method & path | Permission | Notes |
|---|---|---|
| `GET` | `extraction:read` | `ExtractionOut`: `document_status`, current `run` (`version`, `status` running/completed/failed, `trigger`, `error_code`, `error_message`, `summary`, `llm_used`), `tables[]`, open-finding counts by severity. `run` is null until a run exists. |
| `GET /tables/{table_id}/rows?limit&offset&flagged_only` | `extraction:read` | `Page<RowOut>`: `{row_index (source row number), source_ref, raw: {col: {v, t}}, normalized: {col: string\|null}, flags[]}`. limit 1-200. Amounts are fixed-point Decimal strings (`"1234.50"`), dates ISO (`"2025-06-30"`). |
| `PATCH /tables/{table_id}/columns/{col_index}` `{role}` | `extraction:review` | Sets the confirmed role, recomputes normalized values for the table, resolves related findings. 422 unknown role, 404 unknown table/column. Returns `TableOut`. |
| `PATCH /tables/{table_id}` `{confirmed_type}` | `extraction:review` | Sets the confirmed document type. 422 unknown type. |
| `GET /findings?status&severity` | `extraction:read` | Ordered error, warning, info. |
| `PATCH /findings/{finding_id}` `{status: open\|resolved\|dismissed, note?}` | `extraction:review` | `error` findings cannot be dismissed (422). |
| `POST /rerun` -> 202 | `extraction:run` | Queues the document; 409 if already queued/uploaded/processing. A new run version is created; confirmed roles/types carry over. |

`TableOut`: `{id, ordinal, name, kind, n_rows, n_cols, header_row, has_header, detected_type, type_confidence,
type_source (heuristic|llm), confirmed_type, effective_type, currency, period_start, period_end,
status (ok|needs_review|ignored), open_findings, columns[]}`; column: `{col_index, letter, header,
header_synthetic, suggested_role, confidence, role_source (header|content|combined|llm|none),
confirmed_role, effective_role}`.

Column roles: account_code, account_name, description, date, value_date, debit, credit, withdrawal, deposit,
amount, balance, quantity, unit_cost, reference, party, currency, item_code, cost, depreciation,
accumulated_depreciation, net_book_value, gross_pay, deductions, net_pay, other, ignore.
Document types: trial_balance, general_ledger, bank_statement, sales_ledger, purchase_ledger,
fixed_asset_register, inventory_report, payroll_schedule, text_document, unknown. (These describe the
*client's file*; the system holds no ledger.)

Finding codes (non-exhaustive): `hidden_sheet`, `rows_truncated`, `extra_blocks_ignored`, `no_header_row`,
`blank_rows_skipped`, `unknown_document_type`, `type_mismatch`, `low_confidence_column`,
`llm_suggested_role`, `llm_suggested_type`, `ambiguous_date_order`, `date_order_inferred`,
`mixed_date_formats`, `invalid_amounts`, `european_number_format`, `ambiguous_currency`,
`period_mismatch`, `ocr_applied`, `ocr_unavailable`, `no_table_found`, `spreadsheet_errors`.
Row flags: `total_row`, `duplicate_row`, `invalid_amount`, `invalid_date`, `ambiguous_date`,
`sign_convention`, `no_amounts`.

Run failure codes (`run.error_code`): `corrupt_file`, `encrypted_file`, `empty_file`, `no_content`,
`file_too_large`, `too_many_pages`, `unsupported_type`, `ocr_unavailable`, `ocr_timeout`, `ocr_failed`,
`interrupted`, `persist_failed`, `internal_error`. Messages are user-safe (no stack traces or paths).

## LLM gateway and model settings (Phase 4) - `/llm`
All responses are metadata only: aliases, display names, capabilities - never keys or provider model ids.
Unknown or unapproved aliases: 404 on paths, 422 in bodies. Every mutating call returns `{config_version}`.

| Endpoint | Permission | Notes |
|---|---|---|
| `GET /llm/models` | `llm:read` | Approved models with `enabled`, `available` (null if the gateway is unreachable), `used_by`; `config_version`. |
| `PUT /llm/models/{alias}/enabled` `{enabled}` | `llm:manage` | 409 when disabling a model used as an agent default/fallback/override. |
| `POST /llm/models/{alias}/test` | `llm:manage` | Tiny live call; returns `{ok, alias, latency_ms, attempts, error_code}`. Audited. |
| `GET /llm/agents` | `llm:read` | The four agents, defaults, fallbacks, eligible aliases, tasks (effective alias + source), `allow_task_overrides`. |
| `PUT /llm/agents/{agent}` `{default_alias, fallback_alias?}` | `llm:manage` | 422 with reasons when not enabled, incapable, or fallback equals default. |
| `PUT` / `DELETE /llm/agents/{agent}/tasks/{task}` `{alias}` | `llm:select` | 403 unless policy allows; same validation as above. |
| `PUT /llm/policy` `{allow_task_overrides}` | `llm:manage` | |
| `GET /llm/usage?limit&offset&agent` | `llm:manage` | Newest first; limit 1-200. |
| `GET /llm/usage/summary` | `llm:manage` | Per alias+agent: calls, errors, fallbacks, tokens, cost, average latency. |

Gateway error codes (internal, user-safe): `model_unavailable`, `input_too_large`, `llm_call_failed`.

## Audit
`GET /audit-events?limit&offset&action&client_id&actor_user_id&since&until` - `audit:read`.
Firm Admin: whole firm. Others with the permission: only events tied to their assigned clients.

## Health (unchanged from Phase 0)
`GET /health/live`, `GET /health/ready`.

## Kafka Topics and Workers (Phase 5) - `/kafka`
| Method & path | Permission | Notes |
|---|---|---|
| `GET /kafka/topics` | `user:manage` | Returns list of configured Kafka topics, their descriptions, DLQ topic names, and consumer groups. |

## Accounting Review & Reconciliation (Phase 6) - `/clients/{client_id}/periods/{period_id}/review`
| Method & path | Permission | Notes |
|---|---|---|
| `POST /` `{modules?: string[]}` | `review:manage` | 201 `ReviewRunOut`. Triggers review run. Idempotent: returns existing active run if already running. |
| `GET /?limit&offset` | `review:read` | `ReviewRunListOut`. Newest runs first. |
| `GET /{review_run_id}` | `review:read` | `ReviewRunOut`. Includes `module_summary` with per-module finding/exception counts. |
| `GET /{review_run_id}/findings?module&severity&status&limit&offset` | `review:read` | `ReviewFindingListOut`. Filter findings by module, severity, and resolution status. |
| `PATCH /{review_run_id}/findings/{finding_id}` `{status, reviewer_note?}` | `review:resolve` | 200 `ReviewFindingOut`. Status transitions: `open` -> `explained` -> `resolved` / `escalated`. |
| `GET /{review_run_id}/schedules` | `review:read` | `list[ReconciliationScheduleOut]`. All schedules generated during the run (e.g. AR ageing, bank recon). |
| `GET /{review_run_id}/schedules/{schedule_id}` | `review:read` | `ReconciliationScheduleOut`. Detailed data payload of a specific schedule. |

## Period-End Adjustments (Phase 7) - `/clients/{client_id}/periods/{period_id}/adjustments`
| Method & path | Permission | Notes |
|---|---|---|
| `GET /?status&category&limit&offset` | `adjustment:read` | `AdjustmentListOut`. Filter by status (draft, proposed, approved, rejected) and category. |
| `POST /generate` | `adjustment:propose` | 201 `list[PeriodAdjustmentOut]`. Triggers Agent 3 to calculate proposed depreciation, prepayments, accruals, and provisions. |
| `POST /` `{category, debit_account_code, ..., amount, rationale}` | `adjustment:propose` | 201 `PeriodAdjustmentOut`. Manually propose an adjustment. |
| `GET /{adjustment_id}` | `adjustment:read` | `PeriodAdjustmentOut`. Includes immutable calculation breakdown and audit history. |
| `PATCH /{adjustment_id}` `{amount?, debit_account_code?, ...}` | `adjustment:propose` | 200 `PeriodAdjustmentOut`. Version is bumped. If previously approved, approval is invalidated! |
| `POST /{adjustment_id}/decision` `{decision: approved\|rejected, comments?}` | `adjustment:approve` | 200 `PeriodAdjustmentOut`. Formal CA review decision. Only approved adjustments feed reporting. |

## Financial Reporting & Validation (Phase 8) - `/clients/{client_id}/periods/{period_id}/reports`
| Method & path | Permission | Notes |
|---|---|---|
| `POST /generate` `{currency?}` | `report:generate` | 201. Generates Adjusted Trial Balance (Original TB + Approved Adjustments ONLY), Balance Sheet, P&L, Cash Flows, and runs validation engine. |
| `GET /?report_type` | `report:read` | `FinancialReportListOut`. Lists generated reporting packs. |
| `GET /{report_id}` | `report:read` | `FinancialReportOut`. Includes full statements data and validation check results. |
| `POST /{report_id}/sign-off` `{notes?}` | `report:sign_off` | 200 `FinancialReportOut`. Formal CA sign-off. |
| `GET /{report_id}/export/excel` | `report:read` | Streams formatted OpenPyXL workbook with Adjusted TB, P&L, Balance Sheet, and validation tabs. |

## Workflows Orchestration (Phase 9) - `/clients/{client_id}/periods/{period_id}/workflows`
| Method & path | Permission | Notes |
|---|---|---|
| `POST /` | `workflow:execute` | 201 `WorkflowRunOut`. Starts end-to-end LangGraph coordination of Agents 1 through 4. |
| `GET /` | `workflow:read` | `list[WorkflowRunOut]`. Lists historical and active workflow runs. |
| `GET /{workflow_id}` | `workflow:read` | `WorkflowRunOut`. Shows current step, state data, and checkpoint ID. |
| `POST /{workflow_id}/resume` | `workflow:execute` | 200 `WorkflowRunOut`. Resumes execution after CA approval checkpoint. |
