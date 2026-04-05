"""Health check endpoint."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import settings

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    version: str
    env: str


@router.get("", response_model=HealthResponse, summary="Health check")
async def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        version=settings.app_version,
        env=settings.app_env,
    )
