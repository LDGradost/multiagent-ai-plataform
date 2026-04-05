"""
Pydantic schemas (DTOs) for the Agents API.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator


# ── Request schemas ───────────────────────────────────────────────────────────

class AgentCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, examples=["Impresoras HP"])
    description: str = Field(default="", max_length=2000)
    topic: str = Field(..., min_length=1, max_length=255, examples=["HP Printer Support"])
    system_prompt: str = Field(
        ...,
        min_length=10,
        examples=["You are an expert on HP printers. Answer only based on official HP documentation."],
    )
    llm_model: Optional[str] = Field(
        default=None,
        examples=["anthropic.claude-3-5-sonnet-20241022-v2:0"],
    )
    llm_temperature: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    llm_max_tokens: Optional[int] = Field(default=None, ge=256, le=8192)
    embedding_model: Optional[str] = Field(default=None)

    @field_validator("name")
    @classmethod
    def name_no_whitespace_only(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("name cannot be whitespace only")
        return v.strip()


class AgentUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = Field(default=None, max_length=2000)
    topic: Optional[str] = Field(default=None, min_length=1, max_length=255)
    system_prompt: Optional[str] = Field(default=None, min_length=10)
    llm_model: Optional[str] = None
    llm_temperature: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    llm_max_tokens: Optional[int] = Field(default=None, ge=256, le=8192)
    is_active: Optional[bool] = None


# ── Response schemas ──────────────────────────────────────────────────────────

class KnowledgeBaseResponse(BaseModel):
    id: str
    pinecone_index: str
    pinecone_namespace: str
    embedding_model: str
    embedding_dimension: int
    status: str
    total_documents: int
    total_chunks: int
    created_at: datetime


class AgentResponse(BaseModel):
    id: str
    user_id: str
    name: str
    description: str
    topic: str
    system_prompt: str
    pinecone_namespace: str
    embedding_model: str
    llm_model: str
    llm_temperature: float
    llm_max_tokens: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
    knowledge_base: Optional[KnowledgeBaseResponse] = None


class AgentListResponse(BaseModel):
    total: int
    agents: list[AgentResponse]
