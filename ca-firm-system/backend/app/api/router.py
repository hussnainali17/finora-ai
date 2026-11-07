from fastapi import APIRouter

from app.api import audit, auth, clients, documents, extraction, health, llm, users

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(clients.router)
api_router.include_router(documents.router)
api_router.include_router(extraction.router)
api_router.include_router(llm.router)
api_router.include_router(audit.router)
# Later phases register documents, extraction, review, adjustments and reporting routers here.
