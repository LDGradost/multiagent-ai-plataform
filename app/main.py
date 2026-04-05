"""
FastAPI application entry point.
"""
from __future__ import annotations

import contextlib

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.api.v1.router import api_router
from app.api.exception_handlers import register_exception_handlers
from app.infrastructure.db.session import engine, Base

logger = get_logger(__name__)


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[type-arg]
    """Application lifespan: startup and shutdown events."""
    configure_logging()
    logger.info(
        "Starting application",
        name=settings.app_name,
        version=settings.app_version,
        env=settings.app_env,
    )
    # In development/test, create all tables automatically.
    # In production, use Alembic migrations instead.
    if settings.app_env != "production":
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables verified / created")

    yield  # Application runs here

    logger.info("Application shutting down")
    await engine.dispose()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="Multi-Agent AI Platform with RAG, LangGraph, Bedrock and Pinecone",
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        lifespan=lifespan,
    )

    # ── CORS ─────────────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health():
        return {"status": "ok"}

    # ── Routes ────────────────────────────────────────────────────────────────
    app.include_router(api_router, prefix=settings.api_prefix)

    # ── Exception handlers ────────────────────────────────────────────────────
    register_exception_handlers(app)

    return app


app = create_app()
