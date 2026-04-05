"""
API v1 router — aggregates all endpoint modules.
"""
from fastapi import APIRouter

from app.api.v1.endpoints import agents, documents, chat

api_router = APIRouter()

# Agents CRUD
api_router.include_router(
    agents.router,
    prefix="/agents",
    tags=["Agents"],
)

# Documents — nested under /agents but also /documents for standalone delete
api_router.include_router(
    documents.router,
    prefix="/agents",
    tags=["Documents"],
)

# Chat — orchestration + sessions
api_router.include_router(
    chat.router,
    prefix="/chat",
    tags=["Chat"],
)
