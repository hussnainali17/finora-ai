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
