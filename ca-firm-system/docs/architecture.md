# Architecture (Phase 0 + Phase 1)

The CA Firm System is an **accounting review and financial reporting platform**. Clients keep their own books;
this system imports their exports, reviews and reconciles them, proposes adjustments (kept separate until CA
approval) and produces reporting outputs. It is **not** a bookkeeping package: no ledger, no journal posting.

## Runtime topology (local)

```
Browser ──> Nginx :8080 ──> /      Frontend (React + MUI, Vite dev server)
                       └──> /api/  Backend (FastAPI)
                                      ├── PostgreSQL   (application/workflow data, never a ledger)
                                      ├── Redis        (cache / short-lived coordination)
                                      ├── MinIO (S3)   (immutable original files + generated artifacts)
                                      ├── Kafka (KRaft) <── Worker(s) (Python consumers)
                                      └── LiteLLM Proxy ──> LLM providers (keys live only here)
```

## Boundaries established in Phase 0
- Modular monolith backend + separately scalable worker container.
- The browser only talks to the backend (through Nginx). It never calls LiteLLM, Kafka, MinIO or Postgres.
- Provider API keys are read only by the `litellm` container. The backend holds a LiteLLM key (master key in
  Phase 0; a scoped virtual key from Phase 4).
- Kafka = async transport; LangGraph (Phase 9) = workflow state. Neither replaces the other.
- Empty package skeletons (`agents/`, `accounting/`, `workflows/`, ...) mark where later phases land.

## Identity and tenancy (Phase 1)
- Request flow: `Bearer token -> get_principal (DB lookup of user/role/session) -> route permission check ->
  service (re-checks permission, scopes every query by firm and client assignment) -> audit event in the
  same transaction`.
- Full schema, authorization matrix and auth design: [database-design.md](database-design.md);
  endpoints: [api-contracts.md](api-contracts.md).
- Migrations run as a one-shot `migrate` container; the backend waits for it.

## Health model
- `GET /api/v1/health/live` - process is up (no dependency calls).
- `GET /api/v1/health/ready` - checks Postgres, Redis, Kafka, MinIO, LiteLLM; 503 if any fails. Failure details
  contain only the exception class name.
- Worker: `GET /health/live`, `GET /health/ready` on port 8001.
- Kafka readiness is TCP-level in Phase 0; Phase 5 upgrades it to a metadata request.

## Out of scope (permanently)
Ledger/bookkeeping, journal posting, tax, audit execution. See the roadmap README.
