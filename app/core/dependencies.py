"""
Dependency injection container for infrastructure clients.

Provides singletons for all clients so they are initialized once
and reused across the application lifetime.

Usage in FastAPI routes / services:
    from app.core.dependencies import get_embedding_client, get_pinecone_client, ...
"""
from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.session import get_db_session
from app.infrastructure.embeddings.google_embedding_client import (
    GoogleEmbeddingClient,
    IEmbeddingClient,
)
from app.infrastructure.pinecone.pinecone_client import PineconeClient
from app.infrastructure.bedrock.bedrock_client import BedrockClient
from app.infrastructure.storage.s3_client import S3StorageClient
from app.infrastructure.parsers.document_parser import DocumentParserRegistry
from app.infrastructure.db.repositories.agent_repository import (
    AgentRepository,
    KnowledgeBaseRepository,
)
from app.infrastructure.db.repositories.document_repository import (
    DocumentRepository,
    DocumentChunkRepository,
)
from app.infrastructure.db.repositories.chat_repository import (
    ChatSessionRepository,
    ChatMessageRepository,
)


# ─────────────────────────────────────────────────────────────────────────────
# Singleton clients (initialized once at startup)
# ─────────────────────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def get_embedding_client() -> IEmbeddingClient:
    return GoogleEmbeddingClient()


@lru_cache(maxsize=1)
def get_pinecone_client() -> PineconeClient:
    return PineconeClient()


@lru_cache(maxsize=1)
def get_bedrock_client() -> BedrockClient:
    return BedrockClient()


@lru_cache(maxsize=1)
def get_s3_client() -> S3StorageClient:
    return S3StorageClient()


@lru_cache(maxsize=1)
def get_parser_registry() -> DocumentParserRegistry:
    return DocumentParserRegistry()


# ─────────────────────────────────────────────────────────────────────────────
# Repository factories (created per request, bound to the db session)
# ─────────────────────────────────────────────────────────────────────────────

def get_agent_repository(
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> AgentRepository:
    return AgentRepository(db)


def get_kb_repository(
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> KnowledgeBaseRepository:
    return KnowledgeBaseRepository(db)


def get_document_repository(
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> DocumentRepository:
    return DocumentRepository(db)


def get_chunk_repository(
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> DocumentChunkRepository:
    return DocumentChunkRepository(db)


def get_chat_session_repository(
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> ChatSessionRepository:
    return ChatSessionRepository(db)


def get_chat_message_repository(
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> ChatMessageRepository:
    return ChatMessageRepository(db)


# ─────────────────────────────────────────────────────────────────────────────
# Type aliases for clean injection in endpoints
# ─────────────────────────────────────────────────────────────────────────────

DBSession = Annotated[AsyncSession, Depends(get_db_session)]
EmbeddingClientDep = Annotated[IEmbeddingClient, Depends(get_embedding_client)]
PineconeClientDep = Annotated[PineconeClient, Depends(get_pinecone_client)]
BedrockClientDep = Annotated[BedrockClient, Depends(get_bedrock_client)]
S3ClientDep = Annotated[S3StorageClient, Depends(get_s3_client)]
ParserRegistryDep = Annotated[DocumentParserRegistry, Depends(get_parser_registry)]
AgentRepoDep = Annotated[AgentRepository, Depends(get_agent_repository)]
KBRepoDep = Annotated[KnowledgeBaseRepository, Depends(get_kb_repository)]
DocumentRepoDep = Annotated[DocumentRepository, Depends(get_document_repository)]
ChunkRepoDep = Annotated[DocumentChunkRepository, Depends(get_chunk_repository)]
ChatSessionRepoDep = Annotated[ChatSessionRepository, Depends(get_chat_session_repository)]
ChatMessageRepoDep = Annotated[ChatMessageRepository, Depends(get_chat_message_repository)]
