"""
Pydantic schemas (DTOs) for the Chat API.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ── Request schemas ───────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    user_id: str = Field(..., description="ID of the requesting user")
    message: str = Field(..., min_length=1, max_length=10000, description="User's query")
    session_id: Optional[str] = Field(
        default=None,
        description="Existing session ID to continue a conversation",
    )
    agent_id: Optional[str] = Field(
        default=None,
        description="Skip orchestrator and route directly to this agent",
    )
    tenant_id: int = Field(default=1, description="Tenant scope")


# ── Response schemas ──────────────────────────────────────────────────────────

class SourceResponse(BaseModel):
    document_id: str
    filename: str
    chunk_index: int
    page_from: Optional[int]
    page_to: Optional[int]
    score: float


class AgentUsedResponse(BaseModel):
    id: str
    name: str
    topic: str


class ChatResponse(BaseModel):
    message_id: str
    session_id: str
    answer: str
    agent_used: Optional[AgentUsedResponse]
    sources: list[SourceResponse]
    prompt_tokens: int
    completion_tokens: int
    routing_reason: Optional[str]
    error: Optional[str] = None


class ChatMessageResponse(BaseModel):
    id: str
    session_id: str
    role: str
    content: str
    agent_id: Optional[str]
    agent_name: Optional[str]
    sources: list[SourceResponse]
    prompt_tokens: int
    completion_tokens: int
    created_at: datetime


class ChatSessionResponse(BaseModel):
    id: str
    user_id: str
    agent_id: Optional[str]
    title: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ChatHistoryResponse(BaseModel):
    session: ChatSessionResponse
    messages: list[ChatMessageResponse]
