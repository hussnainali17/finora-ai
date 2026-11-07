# Architecture decision log

| # | Decision | Reason |
|---|----------|--------|
| 1 | Monorepo with `frontend/`, `backend/`, `workers/`, `infrastructure/`, `docs/` | Shared versioning, simple CI, matches roadmap. |
| 2 | Modular-monolith FastAPI + separate worker container | Avoid premature microservices; workers scale independently. |
| 3 | `pydantic-settings` with no credential defaults; `SecretStr` | Missing secrets fail fast; secrets never appear in repr/logs. |
| 4 | Placeholder `CHANGE_ME` secrets rejected in staging/production | Prevents shipping template values. |
| 5 | JSON structured logs + `X-Request-ID` correlation ID | Traceability across API, workers and later LangGraph runs. |
| 6 | Plain `postgres:16` image (not pgvector) | pgvector is optional; add only if semantic retrieval is needed. |
| 7 | Single-node Kafka (KRaft) locally | Dev simplicity; production topology decided in Phase 5/11. |
| 8 | Stdlib health server in worker | No extra dependency; Kafka libs arrive in Phase 5. |
| 9 | Ruff + mypy (strict) / ESLint + Prettier + tsc / pytest + Vitest | Quality gates from day one. |
| 10 | MinIO bucket created with versioning enabled | Supports the "original files are immutable" rule from Phase 2. |
| 11 | ~~Auth, DB models and migrations deferred~~ | Implemented in Phase 1 (decisions 12-20). |
| 12 | SQLAlchemy 2 async + Alembic (hand-written migration, `alembic check` in tests) | Matches the FastAPI/asyncpg stack; migration/model drift fails CI. |
| 13 | Self-contained JWT auth (access token + rotating HttpOnly refresh cookie), not Keycloak yet | Roadmap permits either; avoids a heavy service for now. Seam documented in `core/security.py` so OIDC can replace it. |
| 14 | Roles/permissions read from the DB on every request, not stored in the JWT; token carries a session id | Role changes, deactivation, logout and access revocation apply immediately. Cost: one indexed query per request. |
| 15 | Isolation = scoped service layer + composite `(id, firm_id)` FKs + tests; **no Postgres RLS yet** | RLS needs per-request `SET LOCAL` plumbing and a non-owner DB role; deferred to Phase 11 as an additional layer. |
| 16 | Out-of-scope resources return 404, missing permission returns 403 | Does not disclose other firms'/clients' existence. |
| 17 | Roles are global system roles (one per user), not per-firm editable | Simplest model that meets the four roles required. Custom roles would be a later migration. |
| 18 | Emails are globally unique | One login maps to exactly one firm. A firm admin creating an email used by another firm gets a 409 (minor existence disclosure; accepted). |
| 19 | Audit log is append-only via DB triggers; events written in the same transaction | Tamper resistance and atomicity with the change. Hash-chaining/export is a Phase 11 item. |
| 20 | No sign-up endpoint; first firm/admin via `python -m app.cli bootstrap-firm` | Removes an unauthenticated account-creation attack surface. |
| 21 | Files go through the backend (upload and download); no presigned URLs | Keeps firm/client authorisation and audit on every byte in and out. Cost: backend bandwidth; revisit at scale. |
| 22 | Metadata in Postgres, bytes in S3; originals immutable via DB trigger + UUID keys + bucket versioning | "Original files remain unchanged" is enforced by the database, not just by convention. |
| 23 | Soft delete only; the stored object is retained | The client's source evidence is never destroyed by a click. A retention/purge policy is a deliberate later decision. |
| 24 | Duplicate = same SHA-256 live in the same client period (unique partial index) | Safe, explainable rule; allows legitimate reuse across periods and re-upload after removal. |
| 25 | Content verified by magic bytes, not just extension; .xlsm and other formats rejected | Stops renamed executables/macro workbooks. Not a substitute for malware scanning (hook exists, Phase 11). |
| 26 | Transactional outbox + relay for `file.uploaded` (at-least-once) instead of publishing inside the request | An event exists iff the upload committed; survives Kafka outages. Pulls the outbox pattern forward from Phase 5. |
| 27 | Relay runs inside the backend lifespan for now | Simple; safe with replicas via SKIP LOCKED. May move to the worker service in Phase 5. |
| 28 | react-router-dom for client workspace navigation | Deep-linkable client/period/document pages. |
| 29 | Extraction is a deterministic Python pipeline; the LLM only suggests, never decides | "The LLM never calculates and never invents values." The model may choose a column role / document type from a closed list for low-confidence columns; output is validated against the enum, confidence is capped at 0.8, and any LLM-derived role or type keeps the table in *Needs review* until a human confirms it. Heuristics work without the model. |
| 30 | LLM calls go only through the LiteLLM proxy (OpenAI-compatible HTTP, approved model aliases, see 39-46); only headers and up to 5 truncated sample values per column leave the system | One audited egress point. Client data in samples is a privacy consideration; disable with `INTAKE_LLM_ENABLED=false`. |
| 31 | `openpyxl`/`xlrd`/`csv` directly (not pandas); PyMuPDF for digital PDFs; OCRmyPDF + Tesseract for scans and images | Cell coordinates, types and merged cells must survive; pandas discards them. OCR is flagged as a warning finding on every OCR'd file because recognition errors are possible. |
| 32 | Raw cells are stored verbatim (`raw`), normalized values are derived (`normalized`) and re-derivable | Corrections change only the confirmed role/type and recompute `normalized`; the extracted raw data and the original file are never edited. |
| 33 | Ambiguous values are reported, never guessed silently: invalid amounts/dates become `null` + a flag (never 0); ambiguous dates are resolved from the column's other dates, else `INTAKE_DEFAULT_DATE_ORDER`, with a column-level warning; `$` and `Rs` are not mapped to a currency | Wrong silent numbers are worse than a visible gap. |
| 34 | Duplicate and total/subtotal rows are flagged, not removed; extra blocks below/beside the main table are not imported (finding lists them) | Removal is a reviewer decision; the file remains the source of truth. |
| 35 | Each extraction is a versioned `extraction_runs` row (`is_current`); a re-run keeps old runs and carries confirmed roles/types over by (sheet, normalized header) | Reviewer work survives re-runs; history is auditable. Old table ids stop being addressable (404). |
| 36 | The extraction runner polls the database (`uploaded`/`queued` documents, `FOR UPDATE SKIP LOCKED`) inside the backend lifespan, independent of Kafka; stale `running` runs are failed and retried up to 3 times | Works without a broker and is safe with replicas. It does not yet consume `file.uploaded`; moving to an event-driven worker is Phase 5. |
| 37 | Parsing of untrusted files happens in-process with size/page/row/uncompressed caps | Sandboxing (separate process/container, seccomp) is a Phase 11 item; documented as a known risk. |
| 38 | Permissions `extraction:read` (all roles), `extraction:review` and `extraction:run` (Firm Admin, CA/Reviewer, Accountant) | Client users may see what was extracted from their files but cannot change interpretation. Scope rules are unchanged (out-of-scope = 404). |
| 39 | Approved-alias catalog lives in code (`app/llm/catalog.py`) and mirrors `infrastructure/litellm/config.yaml`; a test asserts the two list identical aliases, that keys are `os.environ/` references only, and that LiteLLM retries are off | Firms choose among aliases the platform has vetted; free-text model names are rejected everywhere. Provider model ids stay in the proxy config, never in the API or UI. |
| 40 | **No model is enabled by default**; a firm admin enables models per firm. With none enabled no request leaves the system and Agent 1 uses heuristics only | Client data reaches a provider only after an explicit firm decision. |
| 41 | Per-agent default model + optional explicit fallback; per-task override only when firm policy `allow_task_overrides` is on and the user has `llm:select` | Reviewers can tune a task without the firm losing control. A fallback is never inferred. |
| 42 | Capabilities (structured output, tools, vision) and context window are validated when assigning a model and again at call time; a model that no longer qualifies is skipped; inputs too large for every candidate fail before any request | Wrong-model failures surface at configuration time, not in the middle of a review. Token estimate is deliberately pessimistic (3 chars/token). |
| 43 | The backend owns timeout, bounded retries (exponential backoff on 408/409/425/429/5xx, timeouts, connection errors) and fallback; LiteLLM `num_retries` is 0 | Every attempt is visible and logged by us. Fallback only after availability-class failures (retryable, 401/402/403/404, malformed response) - never on 400, which would fail identically. |
| 44 | `llm_call_logs` is append-only (trigger) and metadata-only: alias, provider, agent/task, client, tokens, cost (from `x-litellm-response-cost`), latency, attempts, fallback, request/correlation ids, `config_version`, error class. **Prompts and completions are never stored** | Cost/latency visibility and audit without retaining client data. Cost is NULL, not 0, when LiteLLM does not report one. A log-write failure never fails a call. |
| 45 | Every configuration change bumps a per-firm `config_version`, is audited (`llm.*`) and is recorded on each call | Any call can be tied to the exact configuration in force. |
| 46 | Errors surfaced to users are generic (`model_unavailable`, `input_too_large`, `llm_call_failed`); provider names, URLs and response bodies are never returned | Avoids leaking provider/key details. Permissions: `llm:read` (admin, reviewer, accountant), `llm:select` (admin, reviewer), `llm:manage` (admin: models, defaults, policy, usage). |
