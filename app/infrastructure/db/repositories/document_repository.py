"""
SQLAlchemy implementation of IDocumentRepository and IDocumentChunkRepository.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.entities import Document, DocumentChunk, DocumentStatus
from app.domain.interfaces.repositories import (
    IDocumentRepository,
    IDocumentChunkRepository,
)
from app.infrastructure.db.models.models import DocumentModel, DocumentChunkModel


def _model_to_document(m: DocumentModel) -> Document:
    return Document(
        id=m.id,
        agent_id=m.agent_id,
        user_id=m.user_id,
        file_name=m.file_name,
        mime_type=m.mime_type,
        file_size_bytes=m.file_size_bytes,
        storage_path=m.storage_path,
        storage_bucket=m.storage_bucket,
        status=DocumentStatus(m.status.value),
        error_message=m.error_message,
        total_chunks=m.total_chunks,
        embedding_model=m.embedding_model,
        chunk_size=m.chunk_size,
        chunk_overlap=m.chunk_overlap,
        uploaded_at=m.uploaded_at,
        processed_at=m.processed_at,
    )


def _model_to_chunk(m: DocumentChunkModel) -> DocumentChunk:
    return DocumentChunk(
        id=m.id,
        document_id=m.document_id,
        agent_id=m.agent_id,
        chunk_index=m.chunk_index,
        vector_id=m.vector_id,
        text_preview=m.text_preview,
        page_from=m.page_from,
        page_to=m.page_to,
        token_count=m.token_count,
        created_at=m.created_at,
    )


class DocumentRepository(IDocumentRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, document: Document) -> Document:
        model = DocumentModel(
            id=document.id,
            agent_id=document.agent_id,
            user_id=document.user_id,
            file_name=document.file_name,
            mime_type=document.mime_type,
            file_size_bytes=document.file_size_bytes,
            storage_path=document.storage_path,
            storage_bucket=document.storage_bucket,
            status=document.status.value,
            embedding_model=document.embedding_model,
            chunk_size=document.chunk_size,
            chunk_overlap=document.chunk_overlap,
        )
        self._session.add(model)
        await self._session.flush()
        return _model_to_document(model)

    async def get_by_id(self, document_id: str) -> Optional[Document]:
        result = await self._session.execute(
            select(DocumentModel).where(DocumentModel.id == document_id)
        )
        model = result.scalar_one_or_none()
        return _model_to_document(model) if model else None

    async def list_by_agent(self, agent_id: str) -> list[Document]:
        result = await self._session.execute(
            select(DocumentModel)
            .where(DocumentModel.agent_id == agent_id)
            .order_by(DocumentModel.uploaded_at.desc())
        )
        return [_model_to_document(m) for m in result.scalars().all()]

    async def update_status(
        self,
        document_id: str,
        status: str,
        error_message: Optional[str] = None,
    ) -> None:
        values: dict = {"status": status}
        if error_message is not None:
            values["error_message"] = error_message
        await self._session.execute(
            update(DocumentModel)
            .where(DocumentModel.id == document_id)
            .values(**values)
        )

    async def update_after_processing(
        self,
        document_id: str,
        total_chunks: int,
        embedding_model: str,
    ) -> None:
        await self._session.execute(
            update(DocumentModel)
            .where(DocumentModel.id == document_id)
            .values(
                status=DocumentStatus.READY.value,
                total_chunks=total_chunks,
                embedding_model=embedding_model,
                processed_at=datetime.now(timezone.utc),
            )
        )

    async def delete(self, document_id: str) -> None:
        result = await self._session.execute(
            select(DocumentModel).where(DocumentModel.id == document_id)
        )
        model = result.scalar_one_or_none()
        if model:
            await self._session.delete(model)
            await self._session.flush()


class DocumentChunkRepository(IDocumentChunkRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def bulk_create(self, chunks: list[DocumentChunk]) -> None:
        models = [
            DocumentChunkModel(
                id=c.id,
                document_id=c.document_id,
                agent_id=c.agent_id,
                chunk_index=c.chunk_index,
                vector_id=c.vector_id,
                text_preview=c.text_preview[:512],
                page_from=c.page_from,
                page_to=c.page_to,
                token_count=c.token_count,
            )
            for c in chunks
        ]
        self._session.add_all(models)
        await self._session.flush()

    async def list_by_document(self, document_id: str) -> list[DocumentChunk]:
        result = await self._session.execute(
            select(DocumentChunkModel)
            .where(DocumentChunkModel.document_id == document_id)
            .order_by(DocumentChunkModel.chunk_index)
        )
        return [_model_to_chunk(m) for m in result.scalars().all()]

    async def delete_by_document(self, document_id: str) -> None:
        result = await self._session.execute(
            select(DocumentChunkModel).where(
                DocumentChunkModel.document_id == document_id
            )
        )
        for model in result.scalars().all():
            await self._session.delete(model)
        await self._session.flush()
