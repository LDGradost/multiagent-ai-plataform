"""
UploadDocumentService — handles file upload and triggers the ingestion pipeline.

Business flow:
1. Validate file type and size
2. Upload raw file to S3
3. Persist Document record in PostgreSQL (status=uploaded)
4. Trigger ProcessDocumentService (sync in dev, async queue in prod)
5. Return document record immediately (processing happens in background)
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import BackgroundTasks

from app.core.config import settings
from app.core.exceptions import (
    AgentNotFoundError,
    FileTooLargeError,
    InvalidFileTypeError,
)
from app.core.logging import get_logger
from app.domain.entities.entities import Document, DocumentStatus
from app.infrastructure.db.repositories.agent_repository import (
    AgentRepository,
    KnowledgeBaseRepository,
)
from app.infrastructure.db.repositories.document_repository import (
    DocumentRepository,
    DocumentChunkRepository,
)
from app.infrastructure.db.session import AsyncSessionFactory
from app.infrastructure.db.repositories.document_repository import (
    DocumentRepository as _DocumentRepository,
    DocumentChunkRepository as _DocumentChunkRepository,
)
from app.infrastructure.db.repositories.agent_repository import KnowledgeBaseRepository as _KBRepository
from app.infrastructure.storage.s3_client import S3StorageClient
from app.infrastructure.embeddings.google_embedding_client import IEmbeddingClient
from app.infrastructure.pinecone.pinecone_client import PineconeClient
from app.infrastructure.parsers.document_parser import DocumentParserRegistry
from app.application.services.vector_ingestion_service import VectorIngestionService

logger = get_logger(__name__)


@dataclass
class UploadDocumentInput:
    agent_id: str
    user_id: str
    filename: str
    content: bytes
    content_type: str


@dataclass
class UploadDocumentOutput:
    document: Document
    processing_started: bool


class UploadDocumentService:
    """
    Use case: validate, store, and trigger processing of an uploaded document.
    """

    def __init__(
        self,
        agent_repo: AgentRepository,
        kb_repo: KnowledgeBaseRepository,
        document_repo: DocumentRepository,
        chunk_repo: DocumentChunkRepository,
        s3_client: S3StorageClient,
        embedding_client: IEmbeddingClient,
        pinecone_client: PineconeClient,
        parser_registry: DocumentParserRegistry,
    ) -> None:
        self._agent_repo = agent_repo
        self._kb_repo = kb_repo
        self._document_repo = document_repo
        self._chunk_repo = chunk_repo
        self._s3 = s3_client
        self._embedding = embedding_client
        self._pinecone = pinecone_client
        self._parser = parser_registry

    async def execute(
        self,
        data: UploadDocumentInput,
        background_tasks: BackgroundTasks,
    ) -> UploadDocumentOutput:
        # ── 1. Validate agent exists and belongs to user ──────────────────────
        agent = await self._agent_repo.get_by_id(data.agent_id)
        if not agent or not agent.is_active:
            raise AgentNotFoundError(data.agent_id)

        # ── 2. Validate file ──────────────────────────────────────────────────
        ext = data.filename.rsplit(".", 1)[-1].lower() if "." in data.filename else ""
        if ext not in settings.allowed_extensions:
            raise InvalidFileTypeError(ext)
        if len(data.content) > settings.max_file_size_bytes:
            raise FileTooLargeError(settings.max_file_size_mb)

        # ── 3. Upload to S3 ───────────────────────────────────────────────────
        document_id = str(uuid.uuid4())
        upload_result = await self._s3.upload_file(
            file_content=data.content,
            agent_id=data.agent_id,
            document_id=document_id,
            filename=data.filename,
            content_type=data.content_type,
        )

        # ── 4. Persist Document record in its own committed session ──────────
        # CRITICAL: FastAPI background tasks run BEFORE get_db_session()
        # commits the request transaction. If we use the request-scoped
        # session the document row won't be visible when the background task
        # tries to INSERT document_chunks (FK violation). We open a dedicated
        # session and commit immediately so the record is DB-visible.
        document = Document(
            id=document_id,
            agent_id=data.agent_id,
            user_id=data.user_id,
            file_name=data.filename,
            mime_type=data.content_type,
            file_size_bytes=len(data.content),
            storage_path=upload_result.key,
            storage_bucket=upload_result.bucket,
            status=DocumentStatus.UPLOADED,
            error_message=None,
            total_chunks=0,
            embedding_model=agent.embedding_model,
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
            uploaded_at=datetime.now(timezone.utc),
            processed_at=None,
        )
        async with AsyncSessionFactory() as doc_session:
            doc_repo = _DocumentRepository(doc_session)
            created_doc = await doc_repo.create(document)
            await doc_session.commit()

        # ── 5. Trigger background processing ─────────────────────────────────
        background_tasks.add_task(
            self._process_document,
            document_id=document_id,
            content=data.content,
            filename=data.filename,
            agent_id=data.agent_id,
            namespace=agent.pinecone_namespace,
        )

        logger.info(
            "Document uploaded, processing queued",
            document_id=document_id,
            agent_id=data.agent_id,
            filename=data.filename,
        )

        return UploadDocumentOutput(document=created_doc, processing_started=True)

    async def _process_document(
        self,
        document_id: str,
        content: bytes,
        filename: str,
        agent_id: str,
        namespace: str,
    ) -> None:
        """
        Background task: parse → chunk → embed → upsert → update status.

        IMPORTANT: This runs AFTER the HTTP request has ended, so the
        request-scoped DB session is already closed. We open a fresh
        independent session here so all DB writes are properly committed.
        """
        async with AsyncSessionFactory() as session:
            try:
                # Fresh repos bound to the new session
                doc_repo = _DocumentRepository(session)
                chunk_repo = _DocumentChunkRepository(session)
                kb_repo = _KBRepository(session)

                await doc_repo.update_status(
                    document_id, DocumentStatus.PROCESSING.value
                )
                await session.commit()

                # Parse text from raw bytes
                text = self._parser.parse(content, filename)
                if not text.strip():
                    raise ValueError("Document produced no extractable text")

                # Ingest into Pinecone + persist chunks in DB
                ingestion_svc = VectorIngestionService(
                    embedding_client=self._embedding,
                    pinecone_client=self._pinecone,
                    chunk_repo=chunk_repo,
                )
                result = await ingestion_svc.ingest(
                    text=text,
                    document_id=document_id,
                    agent_id=agent_id,
                    namespace=namespace,
                    filename=filename,
                )

                # Mark document as ready
                await doc_repo.update_after_processing(
                    document_id=document_id,
                    total_chunks=result.total_chunks,
                    embedding_model=result.embedding_model,
                )

                # Update KB counters
                kb = await kb_repo.get_by_agent_id(agent_id)
                if kb:
                    await kb_repo.update_counts(
                        kb_id=kb.id,
                        documents_delta=1,
                        chunks_delta=result.total_chunks,
                    )

                await session.commit()

                logger.info(
                    "Document processing complete",
                    document_id=document_id,
                    total_chunks=result.total_chunks,
                )

            except Exception as exc:
                await session.rollback()
                logger.error(
                    "Document processing failed",
                    document_id=document_id,
                    error=str(exc),
                )
                # Open another session just for the error status update
                async with AsyncSessionFactory() as err_session:
                    try:
                        err_doc_repo = _DocumentRepository(err_session)
                        await err_doc_repo.update_status(
                            document_id,
                            DocumentStatus.FAILED.value,
                            error_message=str(exc),
                        )
                        await err_session.commit()
                    except Exception as inner_exc:
                        logger.error(
                            "Failed to mark document as FAILED",
                            document_id=document_id,
                            error=str(inner_exc),
                        )
                        await err_session.rollback()
