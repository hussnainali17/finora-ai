# Database migrations (Alembic)

Alembic reads `DATABASE_URL` from the process environment first, then from the backend `.env` file.
If the URL includes `schema=...`, the schema is applied through PostgreSQL's `search_path`.

```bash
export DATABASE_URL=postgresql://USER:PASSWORD@localhost:5432/DBNAME
alembic upgrade head        # build / upgrade the schema
alembic downgrade base      # DESTRUCTIVE: drops everything (dev/test only)
alembic check               # fails if the ORM models differ from the migrations
alembic revision -m "msg"   # new migration (hand-write; review constraints and names)
```

Docker: `make migrate` (also runs automatically before the backend starts).

Rules: migrations are append-only once merged; never import application code into a migration (seed data
is a frozen snapshot); never add ledger/journal/posting tables.
