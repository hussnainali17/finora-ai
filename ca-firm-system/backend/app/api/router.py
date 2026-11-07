from fastapi import APIRouter

from app.api import health

api_router = APIRouter()
api_router.include_router(health.router)
# Feature routers (auth, clients, documents, ...) are registered here in later phases.
