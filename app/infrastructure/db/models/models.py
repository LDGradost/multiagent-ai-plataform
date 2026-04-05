"""
SQLAlchemy ORM models for the Multi-Agent AI Platform.

Table structure:
  users → agents → knowledge_bases
                → documents → document_chunks
  users → chat_sessions → chat_messages
  agents → chat_sessions
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum as PyEnum
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.infrastructure.db.session import Base


# ─────────────────────────────────────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────────────────────────────────────

class DocumentStatus(str, PyEnum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class KnowledgeBaseStatus(str, PyEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class ChatMessageRole(str, PyEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


# ─────────────────────────────────────────────────────────────────────────────
# Helper
# ─────────────────────────────────────────────────────────────────────────────

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


# ─────────────────────────────────────────────────────────────────────────────
# users
# ─────────────────────────────────────────────────────────────────────────────

class UserModel(Base):
    """
    Application users.
    In a multi-tenant scenario each user belongs to a tenant.
    """
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=_uuid
    )
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, default=1, index=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(512), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, server_default=func.now()
    )

    # Relationships
    agents: Mapped[list["AgentModel"]] = relationship(back_populates="user", lazy="select")
    chat_sessions: Mapped[list["ChatSessionModel"]] = relationship(
        back_populates="user", lazy="select"
    )

    __table_args__ = (
        Index("ix_users_tenant_email", "tenant_id", "email"),
    )


# ─────────────────────────────────────────────────────────────────────────────
# agents
# ─────────────────────────────────────────────────────────────────────────────

class AgentModel(Base):
    """
    Specialized knowledge agent.
    Each agent owns a unique Pinecone namespace.
    """
    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=_uuid
    )
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, default=1, index=True)

    # Core fields (from PROJECT_CONTEXT.md)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    topic: Mapped[str] = mapped_column(String(255), nullable=False)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)

    # Pinecone namespace — format: tenant_{tid}_user{uid}_agent{aid}
    pinecone_namespace: Mapped[str] = mapped_column(
        String(512), nullable=False, unique=True
    )

    # Model configuration
    embedding_model: Mapped[str] = mapped_column(
        String(255), nullable=False, default="text-embedding-004"
    )
    llm_model: Mapped[str] = mapped_column(
        String(255), nullable=False, default="anthropic.claude-3-5-sonnet-20241022-v2:0"
    )

    # Agent-level LLM parameters (can override global settings)
    llm_temperature: Mapped[float] = mapped_column(
        nullable=False, default=0.1
    )
    llm_max_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=4096)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, server_default=func.now()
    )

    # Relationships
    user: Mapped["UserModel"] = relationship(back_populates="agents")
    knowledge_base: Mapped[Optional["KnowledgeBaseModel"]] = relationship(
        back_populates="agent", uselist=False, lazy="select"
    )
    documents: Mapped[list["DocumentModel"]] = relationship(
        back_populates="agent", lazy="select"
    )
    chat_sessions: Mapped[list["ChatSessionModel"]] = relationship(
        back_populates="agent", lazy="select"
    )

    __table_args__ = (
        Index("ix_agents_user_id", "user_id"),
        Index("ix_agents_tenant_active", "tenant_id", "is_active"),
    )


# ─────────────────────────────────────────────────────────────────────────────
# knowledge_bases
# ─────────────────────────────────────────────────────────────────────────────

class KnowledgeBaseModel(Base):
    """
    Logical knowledge base — one per agent.
    Tracks the Pinecone namespace and embedding model used.
    PostgreSQL is the source of truth; Pinecone is the search layer.
    """
    __tablename__ = "knowledge_bases"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=_uuid
    )
    agent_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    pinecone_index: Mapped[str] = mapped_column(String(255), nullable=False)
    pinecone_namespace: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    embedding_model: Mapped[str] = mapped_column(String(255), nullable=False)
    embedding_dimension: Mapped[int] = mapped_column(Integer, nullable=False, default=3072)

    status: Mapped[KnowledgeBaseStatus] = mapped_column(
        Enum(KnowledgeBaseStatus, name="kb_status_enum"),
        default=KnowledgeBaseStatus.ACTIVE,
        nullable=False,
    )

    total_documents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_chunks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, server_default=func.now()
    )

    # Relationships
    agent: Mapped["AgentModel"] = relationship(back_populates="knowledge_base")

    __table_args__ = (
        Index("ix_kb_agent_id", "agent_id"),
    )


# ─────────────────────────────────────────────────────────────────────────────
# documents
# ─────────────────────────────────────────────────────────────────────────────

class DocumentModel(Base):
    """
    Uploaded document record.
    Tracks the original file in S3 and its processing status.
    """
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=_uuid
    )
    agent_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    file_name: Mapped[str] = mapped_column(String(512), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    storage_path: Mapped[str] = mapped_column(String(1024), nullable=False)  # S3 key
    storage_bucket: Mapped[str] = mapped_column(String(255), nullable=False)

    status: Mapped[DocumentStatus] = mapped_column(
        Enum(DocumentStatus, name="document_status_enum"),
        default=DocumentStatus.UPLOADED,
        nullable=False,
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Processing metadata
    total_chunks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    chunk_size: Mapped[int] = mapped_column(Integer, default=1000, nullable=False)
    chunk_overlap: Mapped[int] = mapped_column(Integer, default=200, nullable=False)

    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, server_default=func.now()
    )
    processed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    agent: Mapped["AgentModel"] = relationship(back_populates="documents")
    chunks: Mapped[list["DocumentChunkModel"]] = relationship(
        back_populates="document", lazy="select", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_documents_agent_id", "agent_id"),
        Index("ix_documents_user_id", "user_id"),
        Index("ix_documents_status", "status"),
    )


# ─────────────────────────────────────────────────────────────────────────────
# document_chunks
# ─────────────────────────────────────────────────────────────────────────────

class DocumentChunkModel(Base):
    """
    Individual text chunk produced from a document.
    vector_id maps to the Pinecone vector ID in the agent's namespace.
    """
    __tablename__ = "document_chunks"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=_uuid
    )
    document_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    agent_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), nullable=False, index=True
    )

    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    vector_id: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    text_preview: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    page_from: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    page_to: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    token_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, server_default=func.now()
    )

    # Relationships
    document: Mapped["DocumentModel"] = relationship(back_populates="chunks")

    __table_args__ = (
        Index("ix_chunks_document_id", "document_id"),
        UniqueConstraint("document_id", "chunk_index", name="uq_chunk_doc_index"),
    )


# ─────────────────────────────────────────────────────────────────────────────
# chat_sessions
# ─────────────────────────────────────────────────────────────────────────────

class ChatSessionModel(Base):
    """
    A conversation session between a user and the platform.
    May be tied to a specific agent (direct) or routed via orchestrator.
    """
    __tablename__ = "chat_sessions"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=_uuid
    )
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Null if session is routed dynamically each turn
    agent_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("agents.id", ondelete="SET NULL"),
        nullable=True,
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False, default="New Chat")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, server_default=func.now()
    )

    # Relationships
    user: Mapped["UserModel"] = relationship(back_populates="chat_sessions")
    agent: Mapped[Optional["AgentModel"]] = relationship(back_populates="chat_sessions")
    messages: Mapped[list["ChatMessageModel"]] = relationship(
        back_populates="session", lazy="select", cascade="all, delete-orphan",
        order_by="ChatMessageModel.created_at"
    )

    __table_args__ = (
        Index("ix_sessions_user_id", "user_id"),
        Index("ix_sessions_agent_id", "agent_id"),
    )


# ─────────────────────────────────────────────────────────────────────────────
# chat_messages
# ─────────────────────────────────────────────────────────────────────────────

class ChatMessageModel(Base):
    """
    Individual message within a session.
    sources_json stores the RAG sources as a JSONB array.
    """
    __tablename__ = "chat_messages"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=_uuid
    )
    session_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[ChatMessageRole] = mapped_column(
        Enum(ChatMessageRole, name="message_role_enum"),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # Agent that handled this message (assistant messages only)
    agent_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False), nullable=True
    )
    agent_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # RAG sources: list of {document_id, filename, chunk_index, page_from, page_to}
    sources_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # Usage tracking (tokens)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, server_default=func.now()
    )

    # Relationships
    session: Mapped["ChatSessionModel"] = relationship(back_populates="messages")

    __table_args__ = (
        Index("ix_messages_session_id", "session_id"),
        Index("ix_messages_role", "role"),
    )
