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
| 11 | Auth, DB models and migrations deferred | Phase 1. |
