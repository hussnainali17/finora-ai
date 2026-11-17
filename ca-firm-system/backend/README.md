# CA Firm System — Backend

FastAPI application for CA firm accounting review, document intake, period adjustments, financial reporting, and LangGraph workflow orchestration.

For step-by-step setup instructions, required API keys, environment variables, and run commands, see:
👉 **[HOW_TO_RUN_BACKEND.md](./HOW_TO_RUN_BACKEND.md)**

## Quick Start
```powershell
# 1. Create and configure environment
Copy-Item .env.example .env

# 2. Run database migrations
alembic upgrade head

# 3. Create firm admin
python -m app.cli bootstrap-firm --firm-name "My Firm" --slug "my-firm" --admin-email "admin@example.com" --admin-name "Admin"

# 4. Start Uvicorn
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
API Documentation will be live at: `http://localhost:8000/docs`
