"""
Domain entities — pure Python dataclasses, no framework dependencies.
These are the business objects that flow between layers.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


# ─────────────────────────────────────────────────────────────────────────────
# Enums (mirrored from ORM but kept framework-free)
# ─────────────────────────────────────────────────────────────────────────────

class DocumentStatus(str, Enum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class ChatMessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


# ─────────────────────────────────────────────────────────────────────────────
# Entities
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class User:
    id: str
    tenant_id: int
    email: str
    full_name: str
    is_active: bool
    is_superuser: bool
    created_at: datetime
    updated_at: datetime


@dataclass
class Agent:
    id: str
    user_id: str
    tenant_id: int
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


@dataclass
class KnowledgeBase:
    id: str
    agent_id: str
    pinecone_index: str
    pinecone_namespace: str
    embedding_model: str
    embedding_dimension: int
    status: str
    total_documents: int
    total_chunks: int
    created_at: datetime
    updated_at: datetime


@dataclass
class Document:
    id: str
    agent_id: str
    user_id: Optional[str]
    file_name: str
    mime_type: str
    file_size_bytes: int
    storage_path: str
    storage_bucket: str
    status: DocumentStatus
    error_message: Optional[str]
    total_chunks: int
    embedding_model: str
    chunk_size: int
    chunk_overlap: int
    uploaded_at: datetime
    processed_at: Optional[datetime]


@dataclass
class DocumentChunk:
    id: str
    document_id: str
    agent_id: str
    chunk_index: int
    vector_id: str
    text_preview: str
    page_from: Optional[int]
    page_to: Optional[int]
    token_count: int
    created_at: datetime


@dataclass
class ChatSession:
    id: str
    user_id: str
    agent_id: Optional[str]
    title: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


@dataclass
class ChatSource:
    """Source metadata returned alongside an AI response."""
    document_id: str
    filename: str
    chunk_index: int
    page_from: Optional[int]
    page_to: Optional[int]
    score: float = 0.0


@dataclass
class ChatMessage:
    id: str
    session_id: str
    role: ChatMessageRole
    content: str
    agent_id: Optional[str]
    agent_name: Optional[str]
    sources: list[ChatSource] = field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    created_at: datetime = field(default_factory=datetime.utcnow)
