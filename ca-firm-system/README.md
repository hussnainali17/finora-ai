# CA Firm System

AI-assisted **accounting review and financial reporting** platform for a CA firm. Clients keep their own books and
supply Excel/CSV/PDF records; this system imports, reviews, reconciles and reports on them.
It does **not** create a ledger, post transactions or do bookkeeping, tax or audit work.

> **Status: Phase 1 - database, authentication and tenant isolation.** Users can sign in; firms, clients and
> accounting periods exist with role- and client-level access control and an audit trail. No accounting
> features yet. See the roadmap for the phase plan.

## Stack
React + TypeScript + MUI · FastAPI · PostgreSQL · Redis · Kafka (KRaft) · MinIO · LiteLLM Proxy · Docker Compose · Nginx

## Repository layout
```
frontend/         React + TS + MUI (Vite)
backend/          FastAPI app (api, core, db, models, schemas, services, agents, workflows, accounting, integrations)
workers/          Python Kafka-consumer workers (health server + shutdown only in Phase 0)
infrastructure/   nginx, litellm, kafka, monitoring, docker assets
docs/             architecture, decisions, security, database-design, api-contracts
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
Without `TEST_DATABASE_URL` those tests are skipped (health/config tests still run) - CI always sets it.

## Configuration and secrets
See [docs/security.md](docs/security.md). Short version: `.env` is never committed, provider keys exist only in the
`litellm` container, and the browser only talks to the backend.

## Known limitations
- Docker Compose config was written but not executed in the authoring environment (no Docker daemon there);
  run `docker compose up --build` and report any image-specific issues. Pin `minio/minio`, `minio/mc` and
  `litellm` image tags before staging.
- Kafka readiness is a TCP check; workers do not consume topics yet (Phase 5).
- LiteLLM has no approved models configured yet (Phase 4).
- Phase 1: no MFA, no email-based password reset, no Postgres row-level security, HS256 shared secret; see
  [docs/security.md](docs/security.md). Client/period screens arrive in Phase 2 (the API exists now).
