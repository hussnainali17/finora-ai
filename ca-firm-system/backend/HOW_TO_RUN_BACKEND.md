# CA Firm System — Backend Setup & Execution Guide

This guide explains step-by-step how to configure, set up environment variables and API keys, and run the FastAPI backend server.

---

## 1. Quick Overview

The backend is built with **Python 3.11+**, **FastAPI**, **SQLAlchemy 2 (Async)**, and **Alembic**. It coordinates with:
- **PostgreSQL 16**: Relational storage (firms, users, clients, periods, review findings, adjustments, reports).
- **Redis 7**: Cache & token blocklists.
- **Apache Kafka (KRaft)**: Event streaming (`file-uploaded`, `workflow-status`, etc.).
- **MinIO / S3**: Object storage for immutable raw Excel/PDF/CSV documents.
- **LiteLLM Proxy**: Centralized gateway for AI models (Claude, GPT, Gemini).

---

## 2. Required Configurations & API Keys

Before running the backend, create a configuration file at `backend/.env` (or use the root `.env` if using Docker).

### Step 2.1: Create your `backend/.env` file
Copy the template:
```powershell
# In PowerShell:
Copy-Item backend\.env.example backend\.env
```
Or in CMD / Bash:
```bash
cp backend/.env.example backend/.env
```

---

### Step 2.2: Configuration Keys Breakdown

Here is what you must configure in `backend/.env`:

```env
# =============================================================================
# ENVIRONMENT & LOGGING
# =============================================================================
APP_ENV=local
LOG_LEVEL=INFO

# =============================================================================
# DATABASE (PostgreSQL)
# Format: postgresql://<USER>:<PASSWORD>@<HOST>:<PORT>/<DATABASE>
# =============================================================================
DATABASE_URL=postgresql://cafirm:cafirmpassword123@localhost:5432/cafirm

# =============================================================================
# REDIS (Cache & Sessions)
# Format: redis://:<PASSWORD>@<HOST>:<PORT>/<DB_NUMBER>
# =============================================================================
REDIS_URL=redis://:redispassword123@localhost:6379/0

# =============================================================================
# KAFKA (KRaft Event Bus)
# If running backend on Windows host and Kafka in Docker, use external port 29092
# =============================================================================
KAFKA_BOOTSTRAP_SERVERS=localhost:29092

# =============================================================================
# MINIO (S3-Compatible Object Storage)
# =============================================================================
MINIO_ENDPOINT=http://localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin123
MINIO_BUCKET=ca-firm-files

# =============================================================================
# LITELLM PROXY (AI Gateway)
# All backend AI calls route through LiteLLM at localhost:4000.
# The API key must match the LITELLM_MASTER_KEY configured in LiteLLM.
# =============================================================================
LITELLM_BASE_URL=http://localhost:4000
LITELLM_API_KEY=sk-cafirm-litellm-master-key-12345

# =============================================================================
# AUTHENTICATION & SECURITY
# JWT_SECRET: MUST be at least 32 characters long.
# Generate one using PowerShell: [System.Guid]::NewGuid().ToString() + [System.Guid]::NewGuid().ToString()
# Or in bash: openssl rand -hex 32
# =============================================================================
JWT_SECRET=4f8b9e6c2d1a3f5b7e9a0c2d4e6f8a1b3c5d7e9f0a2b4c6d8e0f1a3b5c7d9e1f
COOKIE_SECURE=false

# =============================================================================
# CORS (Frontend origins allowed to call the backend)
# =============================================================================
CORS_ALLOWED_ORIGINS=["http://localhost:5173", "http://localhost:8080"]
```

---

### Step 2.3: Where to put External AI Provider API Keys

> [!IMPORTANT]
> **Provider API keys (OpenAI, Anthropic, Gemini) are NEVER placed in the backend or frontend code.**
> They are loaded by the **LiteLLM Proxy** in the root `.env` file so they remain strictly isolated on the server.

In the root `.env` file (used by LiteLLM Proxy in Docker):
```env
# Root .env
LITELLM_MASTER_KEY=sk-cafirm-litellm-master-key-12345

# Add at least ONE AI provider key that you have:
GEMINI_API_KEY=AIzaSy...your-gemini-key
# or:
OPENAI_API_KEY=sk-proj-...your-openai-key
# or:
ANTHROPIC_API_KEY=sk-ant-...your-anthropic-key
```

---

## 3. How to Run the Backend

You can run the backend in one of two ways:
- **Option A (Recommended)**: Run infrastructure with Docker Compose, run FastAPI on host.
- **Option B (Full Docker)**: Run the whole stack including backend via Docker Compose.

---

### Method A: Running Backend Locally on Host (Fastest for Dev & Debugging)

#### Step 1: Start Infrastructure Services (Database, Redis, Kafka, MinIO, LiteLLM)
From the root project directory:
```powershell
# Start supporting containers in the background:
docker compose up -d postgres redis kafka minio litellm
```

#### Step 2: Open Terminal in `backend/` Directory
```powershell
cd d:\hussnain\Final-Year-Project\7th-sem-final\Finora\ca-firm-system\backend
```

#### Step 3: Create & Activate Python Virtual Environment
```powershell
# Create venv (Python 3.11 or 3.12 recommended)
python -m venv venv

# Activate venv on Windows (PowerShell):
.\venv\Scripts\Activate.ps1

# (If PowerShell blocks script execution, run: Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass)
# Or in Windows Command Prompt (CMD):
.\venv\Scripts\activate.bat
```

#### Step 4: Install Dependencies
```powershell
pip install --upgrade pip
pip install -e .
```

#### Step 5: Run Database Migrations
Apply all schema tables (Identity, Documents, Extraction, Review, Adjustments, Reporting, Workflows):
```powershell
alembic upgrade head
```

#### Step 6: Bootstrap First Firm & Admin User
Because there is deliberately no public sign-up endpoint, run the bootstrap CLI to create your firm and admin user:
```powershell
python -m app.cli bootstrap-firm `
  --firm-name "Apex Chartered Accountants" `
  --slug "apex-ca" `
  --admin-email "admin@apex.example" `
  --admin-name "Senior Partner"
```
*(You will be prompted to type an admin password securely without echo, e.g., `AdminPass1234!`)*

#### Step 7: Launch the Backend Server
Run Uvicorn with auto-reload:
```powershell
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

---

### Method B: Running via Docker Compose (All-in-One)

If you prefer to run everything in containers:

1. Copy the root environment file:
   ```powershell
   Copy-Item .env.example .env
   ```
2. Open `.env` and fill in:
   - `POSTGRES_PASSWORD` (e.g., `cafirmpassword123`)
   - `REDIS_PASSWORD` (e.g., `redispassword123`)
   - `MINIO_ROOT_PASSWORD` (e.g., `minioadmin123`)
   - `LITELLM_MASTER_KEY` (e.g., `sk-cafirm-litellm-master-key-12345`)
   - `JWT_SECRET` (generate 32+ hex chars)
   - Add your `GEMINI_API_KEY` or `OPENAI_API_KEY`
3. Start the stack:
   ```powershell
   docker compose up --build
   ```
4. In another terminal, bootstrap your firm admin user:
   ```powershell
   docker compose exec backend python -m app.cli bootstrap-firm `
     --firm-name "Apex Chartered Accountants" `
     --slug "apex-ca" `
     --admin-email "admin@apex.example" `
     --admin-name "Senior Partner"
   ```

---

## 4. Verification & Testing

Once running, verify the backend by visiting:

| Feature | URL |
|---|---|
| **Interactive API Documentation (Swagger)** | [http://localhost:8000/docs](http://localhost:8000/docs) |
| **Alternative API Docs (ReDoc)** | [http://localhost:8000/redoc](http://localhost:8000/redoc) |
| **Liveness Check** | [http://localhost:8000/api/v1/health/live](http://localhost:8000/api/v1/health/live) |
| **Readiness Check (DB, Redis, S3, Kafka, LiteLLM)** | [http://localhost:8000/api/v1/health/ready](http://localhost:8000/api/v1/health/ready) |
| **Prometheus Metrics** | [http://localhost:8000/metrics](http://localhost:8000/metrics) |

### Health Check Output
Visiting `http://localhost:8000/api/v1/health/ready` should return:
```json
{
  "status": "ok",
  "dependencies": {
    "database": "ok",
    "redis": "ok",
    "storage": "ok",
    "kafka": "ok",
    "litellm": "ok"
  }
}
```

---

## 5. Summary of Common Commands

| Task | Command |
|---|---|
| Activate venv (PowerShell) | `.\venv\Scripts\Activate.ps1` |
| Install packages | `pip install -e .` |
| Run migrations | `alembic upgrade head` |
| Rollback migration | `alembic downgrade -1` |
| Create admin account | `python -m app.cli bootstrap-firm --firm-name "Firm Name" --slug "slug" --admin-email "admin@example.com" --admin-name "Admin Name"` |
| Start backend server | `uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload` |
| Run tests | `pytest` |
