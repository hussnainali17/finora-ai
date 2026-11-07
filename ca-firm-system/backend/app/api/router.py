from fastapi import APIRouter

from app.api import accounting_review, audit, auth, clients, documents, extraction, health, kafka_topics, llm, users

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(clients.router)
api_router.include_router(documents.router)
api_router.include_router(extraction.router)
api_router.include_router(llm.router)
api_router.include_router(audit.router)
api_router.include_router(accounting_review.router)
api_router.include_router(kafka_topics.router)
# Later phases register adjustments and reporting routers here.
