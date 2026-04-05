"""
Central configuration module using Pydantic Settings.
All values are loaded from environment variables or .env file.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any

from pydantic import Field, PostgresDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    """Application-level settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── App ──────────────────────────────────────────────────────────────────
    app_env: str = Field(default="development")
    app_name: str = Field(default="Multi-Agent AI Platform")
    app_version: str = Field(default="1.0.0")
    secret_key: str = Field(default="change-me")
    debug: bool = Field(default=False)
    log_level: str = Field(default="INFO")

    # ── API ──────────────────────────────────────────────────────────────────
    api_host: str = Field(default="0.0.0.0")
    api_port: int = Field(default=8000)
    api_prefix: str = Field(default="/api/v1")
    cors_origins: list[str] = Field(default=["http://localhost:3000"])

    # ── PostgreSQL ───────────────────────────────────────────────────────────
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/multiagent_db"
    )
    db_pool_size: int = Field(default=10)
    db_max_overflow: int = Field(default=20)
    db_echo: bool = Field(default=False)

    # ── Amazon Bedrock ───────────────────────────────────────────────────────
    aws_access_key_id: str = Field(default="")
    aws_secret_access_key: str = Field(default="")
    aws_region: str = Field(default="us-east-1")
    bedrock_default_model_id: str = Field(
        default="anthropic.claude-3-5-sonnet-20241022-v2:0"
    )
    bedrock_orchestrator_model_id: str = Field(
        default="anthropic.claude-3-haiku-20240307-v1:0"
    )
    bedrock_max_tokens: int = Field(default=4096)
    bedrock_temperature: float = Field(default=0.1)

    # ── Amazon S3 ─────────────────────────────────────────────────────────────
    s3_bucket_name: str = Field(default="multiagent-documents")
    s3_region: str = Field(default="us-east-1")
    s3_prefix: str = Field(default="uploads/")

    # ── Google Gemini Embedding 2 ────────────────────────────────────────────
    # Credentials: set GOOGLE_APPLICATION_CREDENTIALS (Vertex AI / ADC)
    # or GOOGLE_API_KEY (direct API key mode)
    google_application_credentials: str = Field(default="")
    google_api_key: str = Field(default="")  # alternative to service account
    google_cloud_project: str = Field(default="")
    google_cloud_location: str = Field(default="us-central1")  # only us-central1 supported
    # gemini-embedding-2-preview outputs 3072 dims by default (Preview, March 2026)
    google_embedding_model: str = Field(default="gemini-embedding-2-preview")
    # Supports MRL: set to 768 or 1536 to reduce storage size (minor quality loss)
    embedding_dimension: int = Field(default=3072)

    # ── Pinecone ─────────────────────────────────────────────────────────────
    pinecone_api_key: str = Field(default="")
    pinecone_index_name: str = Field(default="multiagent-knowledge")
    pinecone_cloud: str = Field(default="aws")
    pinecone_region: str = Field(default="us-east-1")

    # ── Document Processing ──────────────────────────────────────────────────
    chunk_size: int = Field(default=1000)
    chunk_overlap: int = Field(default=200)
    max_file_size_mb: int = Field(default=50)
    allowed_extensions: list[str] = Field(
        default=["pdf", "docx", "txt", "md"]
    )
    ocr_enabled: bool = Field(default=False)
    ocr_language: str = Field(default="spa")

    # ── Multi-tenancy ────────────────────────────────────────────────────────
    default_tenant_id: int = Field(default=1)

    # ── Background Tasks ─────────────────────────────────────────────────────
    background_worker: str = Field(default="fastapi")
    redis_url: str = Field(default="redis://localhost:6379/0")

    # ── Observability ────────────────────────────────────────────────────────
    sentry_dsn: str = Field(default="")
    enable_tracing: bool = Field(default=False)

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = v.upper()
        if upper not in allowed:
            raise ValueError(f"log_level must be one of {allowed}")
        return upper

    @field_validator("bedrock_temperature")
    @classmethod
    def validate_temperature(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError("bedrock_temperature must be between 0.0 and 1.0")
        return v

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def max_file_size_bytes(self) -> int:
        return self.max_file_size_mb * 1024 * 1024


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    """
    Return a cached singleton of AppSettings.
    Use this everywhere instead of instantiating AppSettings directly.
    """
    return AppSettings()


# Convenience alias
settings = get_settings()
