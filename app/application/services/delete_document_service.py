"""
DeleteDocumentService — removes a document and all its associated data.

Business flow:
1. Verify document exists
2. Delete all vectors from Pinecone (by document_id filter in agent namespace)
3. Delete DocumentChunk records from PostgreSQL
4. Delete original file from S3
5. Delete Document record from PostgreSQL
6. Update KnowledgeBase counters
"""
from __future__ import annotations

from app.core.exceptions import DocumentNotFoundError
from app.core.logging import get_logger
from app.infrastructure.db.repositories.agent_repository import KnowledgeBaseRepository
from app.infrastructure.db.repositories.document_repository import (
    DocumentChunkRepository,
    DocumentRepository,
)
from app.infrastructure.pinecone.pinecone_client import PineconeClient
from app.infrastructure.storage.s3_client import S3StorageClient

logger = get_logger(__name__)


class DeleteDocumentService:
    def __init__(
        self,
        document_repo: DocumentRepository,
        chunk_repo: DocumentChunkRepository,
        kb_repo: KnowledgeBaseRepository,
        pinecone_client: PineconeClient,
        s3_client: S3StorageClient,
    ) -> None:
        self._document_repo = document_repo
        self._chunk_repo = chunk_repo
        self._kb_repo = kb_repo
        self._pinecone = pinecone_client
        self._s3 = s3_client

    async def execute(self, document_id: str) -> None:
        # ── 1. Verify document ────────────────────────────────────────────────
        document = await self._document_repo.get_by_id(document_id)
        if not document:
            raise DocumentNotFoundError(document_id)

        chunk_count = document.total_chunks

        # ── 2. Delete vectors from Pinecone ───────────────────────────────────
        # Get agent namespace for the delete call
        from app.infrastructure.db.repositories.agent_repository import AgentRepository
        # We resolve namespace from the document's agent_id via knowledge_base
        kb = await self._kb_repo.get_by_agent_id(document.agent_id)
        if kb:
            await self._pinecone.delete_by_document(
                namespace=kb.pinecone_namespace,
                document_id=document_id,
            )

        # ── 3. Delete chunk records from PostgreSQL ───────────────────────────
        await self._chunk_repo.delete_by_document(document_id)

        # ── 4. Delete file from S3 ────────────────────────────────────────────
        await self._s3.delete_file(document.storage_path)

        # ── 5. Delete document record ─────────────────────────────────────────
        await self._document_repo.delete(document_id)

        # ── 6. Update KB counters ─────────────────────────────────────────────
        if kb:
            await self._kb_repo.update_counts(
                kb_id=kb.id,
                documents_delta=-1,
                chunks_delta=-chunk_count,
            )

        logger.info(
            "Document deleted",
            document_id=document_id,
            agent_id=document.agent_id,
            chunks_removed=chunk_count,
        )
