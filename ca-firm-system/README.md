# CA Firm System

AI-assisted **accounting review and financial reporting** platform for a CA firm. Clients keep their own books and
supply Excel/CSV/PDF records; this system imports, reviews, reconciles and reports on them.
It does **not** create a ledger, post transactions or do bookkeeping, tax or audit work.

> **Status: Phase 4 - LiteLLM gateway and model selection** (on top of Phase 3 extraction, Agent 1). Firm admins enable
> approved models, set per-agent defaults/fallbacks and see usage under *AI models*; nothing is enabled by default.
>
> Phase 3 - data extraction and structuring (Agent 1). Sign in, browse clients and accounting periods,
> upload client files (stored immutably in object storage), and have them read into structured, reviewable
> tables: Excel/CSV/digital-PDF/scanned (OCR) parsing, table and header detection, document-type and column-role
> classification, date/amount normalization, and data-quality findings. Reviewers confirm or correct column
> roles and document types on a review screen; originals and raw extracted cells are never modified.
> No reconciliation, adjustments or reporting yet. See the roadmap for the phase plan.

## Stack
React + TypeScript + MUI · FastAPI · PostgreSQL · Redis · Kafka (KRaft) · MinIO · LiteLLM Proxy · Docker Compose · Nginx

## Repository layout
```
frontend/         React + TS + MUI (Vite)
backend/          FastAPI app (api, core, db, models, schemas, services, agents, workflows, accounting, integrations)
workers/          Python Kafka-consumer workers (health server + shutdown only in Phase 0)
infrastructure/   nginx, litellm, kafka, monitoring, docker assets
docs/             architecture, decisions, security, database-design, api-contracts, event-contracts
```

## Prerequisites
Docker + Docker Compose v2. For running checks outside Docker: Python 3.11+ and Node 20+ (22 recommended).

## Quick start (Docker)
```bash
cp .env.example .env          # or: make setup
# Edit .env: replace every CHANGE_ME (URL-safe passwords; LITELLM_MASTER_KEY must start with "sk-";
#   JWT_SECRET: `openssl rand -hex 32`)
docker compose up --build     # or: make up
```
Then open:

| Service | URL |
|---|---|
| App (via Nginx) | http://localhost:8080 |
| API docs | http://localhost:8000/docs |
| Backend liveness / readiness | http://localhost:8000/api/v1/health/live · `/ready` |
| Worker health | http://localhost:8001/health/live · `/ready` |
| MinIO console | http://localhost:9001 |
| LiteLLM Proxy | http://localhost:4000 |

Migrations run automatically (`migrate` service). Then create the first firm and admin (there is no sign-up page):
```bash
docker compose exec -e BOOTSTRAP_ADMIN_PASSWORD='choose-a-long-passphrase' backend \
  python -m app.cli bootstrap-firm --firm-name "Acme & Co" --slug acme \
  --admin-email admin@acme.example --admin-name "Ada Admin"
```
Sign in at http://localhost:8080 with that email and password. The home page shows your role/permissions and live readiness of every dependency. First start may take a minute while Kafka and LiteLLM
become healthy (`docker compose ps`).

## Running checks
Without Docker (one-time setup per service):
```bash
cd backend  && python -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"
cd workers  && python -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"
cd frontend && npm install
```
| Task | Backend / Workers | Frontend |
|---|---|---|
| Tests | `pytest` | `npm test` |
| Lint | `ruff check .` · `ruff format --check .` | `npm run lint` · `npm run format:check` |
| Types | `mypy app` / `mypy ca_workers` | `npm run typecheck` |
| Build | - | `npm run build` |

`make lint`, `make test` and `make check` run everything.

**Database-backed backend tests.** Isolation, auth and migration tests run against a real PostgreSQL (they
test composite FKs, exclusion constraints and triggers, which mocks cannot). Point `TEST_DATABASE_URL` at a
**disposable** database - the schema is dropped and rebuilt from the migrations on every run:
```bash
docker compose up -d postgres
docker compose exec postgres createdb -U "$POSTGRES_USER" cafirm_test
export TEST_DATABASE_URL=postgresql://USER:PASSWORD@localhost:5432/cafirm_test
cd backend && pytest
```
Storage tests use an in-process S3 server (moto) and Kafka is faked, so no MinIO/Kafka is needed. Without
`TEST_DATABASE_URL` those tests are skipped (health/config tests still run) - CI always sets it.

**Extraction (Phase 3).** A background runner in the backend picks up `uploaded`/`queued` documents and
extracts them (`INTAKE_ENABLED`). OCR needs the `tesseract-ocr` package (installed in the backend image and in
CI; for local runs: `apt install tesseract-ocr`). The optional AI assist for ambiguous columns calls LiteLLM only
through the gateway (`INTAKE_LLM_*`, `LLM_*`) and is off-switchable (`INTAKE_LLM_ENABLED=false`); heuristics work without it.

**LLM gateway (Phase 4).** Put provider keys in `.env` (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY` - only the
`litellm` container reads them), verify the provider model ids in `infrastructure/litellm/config.yaml`, then sign in as
firm admin -> *AI models*: enable a model, set the Intake agent default (and optional fallback), use *Test*.
Tests call the extraction service directly (`INTAKE_ENABLED=false`).

## Configuration and secrets
See [docs/security.md](docs/security.md). Short version: `.env` is never committed, provider keys exist only in the
`litellm` container, and the browser only talks to the backend.

## Known limitations
- Docker Compose config was written but not executed in the authoring environment (no Docker daemon there);
  run `docker compose up --build` and report any image-specific issues. Pin `minio/minio`, `minio/mc` and
  `litellm` image tags before staging.
- Kafka readiness is a TCP check; workers do not consume topics yet (Phase 5).
- Phase 4: the gateway is tested against scripted/stub HTTP servers only - **a real LiteLLM proxy and real providers were not exercised** in the authoring environment. Provider model ids in `config.yaml` are placeholders to verify. Token counts for the context pre-check are a rough estimate; per-call cost depends on LiteLLM's `x-litellm-response-cost` header. Only one AI task exists (Intake column roles); other agents get tasks in later phases.
- Phase 3: untrusted files are parsed **in-process** (size, page, row and uncompressed-size caps only);
  sandboxing is Phase 11. Detection is heuristic and English-centric; header recognition covers common
  accounting terms, not every language. Column roles are chosen per column, not per row, and merged
  multi-level headers beyond two rows are not combined. The extraction runner polls the database; it does not
  yet consume the `file.uploaded` Kafka event (Phase 5). Extraction results are
  review data, not ledger entries.
- Phase 2: uploaded files are NOT malware-scanned yet (hook only); the Kafka producer is tested with a fake
  broker only (no broker in the authoring environment), and `file.uploaded` has no consumer until Phase 3/5;
  orphan-object reconciliation is Phase 11.
- Phase 1: no MFA, no email-based password reset, no Postgres row-level security, HS256 shared secret; see
  [docs/security.md](docs/security.md). Client/period screens arrive in Phase 2 (the API exists now).
