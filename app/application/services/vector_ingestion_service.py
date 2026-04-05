"""
VectorIngestionService — chunks text and upserts vectors into Pinecone.

Responsibilities:
1. Split extracted text into configurable chunks (with overlap)
2. Generate embeddings via GoogleEmbeddingClient
3. Build VectorRecord with full metadata per chunk
4. Upsert into Pinecone under the agent's namespace
5. Persist DocumentChunk records to PostgreSQL
6. Return chunk count for status updates
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.core.config import settings
from app.core.logging import get_logger
from app.domain.entities.entities import DocumentChunk
from app.infrastructure.db.repositories.document_repository import DocumentChunkRepository
from app.infrastructure.embeddings.google_embedding_client import IEmbeddingClient
from app.infrastructure.pinecone.pinecone_client import PineconeClient, VectorRecord

logger = get_logger(__name__)


@dataclass
class ChunkData:
    """Intermediate chunk with text and page info."""
    text: str
    chunk_index: int
    page_from: Optional[int] = None
    page_to: Optional[int] = None


@dataclass
class IngestionResult:
    total_chunks: int
    vector_ids: list[str]
    embedding_model: str


class VectorIngestionService:
    """
    Chunks, embeds, and indexes a document's text into Pinecone.
    """

    def __init__(
        self,
        embedding_client: IEmbeddingClient,
        pinecone_client: PineconeClient,
        chunk_repo: DocumentChunkRepository,
    ) -> None:
        self._embedding = embedding_client
        self._pinecone = pinecone_client
        self._chunk_repo = chunk_repo

    async def ingest(
        self,
        text: str,
        document_id: str,
        agent_id: str,
        namespace: str,
        filename: str,
        chunk_size: Optional[int] = None,
        chunk_overlap: Optional[int] = None,
    ) -> IngestionResult:
        """
        Full pipeline: split → embed → upsert → persist chunks.
        """
        effective_chunk_size = chunk_size or settings.chunk_size
        effective_overlap = chunk_overlap or settings.chunk_overlap

        # ── 1. Split text into chunks ─────────────────────────────────────────
        chunks = self._split_text(text, effective_chunk_size, effective_overlap)

        if not chunks:
            logger.warning(
                "No chunks produced from document",
                document_id=document_id,
                filename=filename,
            )
            return IngestionResult(
                total_chunks=0, vector_ids=[], embedding_model=self._embedding.model_name
            )

        chunk_texts = [c.text for c in chunks]

        logger.info(
            "Chunking complete",
            document_id=document_id,
            total_chunks=len(chunks),
            chunk_size=effective_chunk_size,
            overlap=effective_overlap,
        )

        # ── 2. Generate embeddings ────────────────────────────────────────────
        vectors = await self._embedding.embed_documents(chunk_texts)

        # ── 3. Build Pinecone records ─────────────────────────────────────────
        vector_ids: list[str] = []
        pinecone_records: list[VectorRecord] = []
        domain_chunks: list[DocumentChunk] = []
        now_iso = datetime.now(timezone.utc).isoformat()

        for i, (chunk, vector) in enumerate(zip(chunks, vectors)):
            vector_id = str(uuid.uuid4())
            vector_ids.append(vector_id)

            # Pinecone metadata — full text is stored here for retrieval
            # NOTE: Pinecone rejects null values; omit page_from/page_to when unknown.
            metadata: dict[str, Any] = {
                "chunk_id": vector_id,
                "document_id": document_id,
                "agent_id": agent_id,
                "filename": filename,
                "text": chunk.text,
                "chunk_index": chunk.chunk_index,
                "created_at": now_iso,
            }
            if chunk.page_from is not None:
                metadata["page_from"] = chunk.page_from
            if chunk.page_to is not None:
                metadata["page_to"] = chunk.page_to

            pinecone_records.append(
                VectorRecord(id=vector_id, values=vector, metadata=metadata)
            )

            domain_chunks.append(
                DocumentChunk(
                    id=str(uuid.uuid4()),
                    document_id=document_id,
                    agent_id=agent_id,
                    chunk_index=chunk.chunk_index,
                    vector_id=vector_id,
                    text_preview=chunk.text[:512],
                    page_from=chunk.page_from,
                    page_to=chunk.page_to,
                    token_count=len(chunk.text.split()),
                    created_at=datetime.now(timezone.utc),
                )
            )

        # ── 4. Upsert to Pinecone ─────────────────────────────────────────────
        await self._pinecone.upsert(namespace=namespace, records=pinecone_records)

        # ── 5. Persist chunks in PostgreSQL ───────────────────────────────────
        await self._chunk_repo.bulk_create(domain_chunks)

        logger.info(
            "Ingestion complete",
            document_id=document_id,
            namespace=namespace,
            total_chunks=len(chunks),
        )

        return IngestionResult(
            total_chunks=len(chunks),
            vector_ids=vector_ids,
            embedding_model=self._embedding.model_name,
        )

    @staticmethod
    def _split_text(
        text: str, chunk_size: int, chunk_overlap: int
    ) -> list[ChunkData]:
        """
        Use LangChain's RecursiveCharacterTextSplitter.
        Preserves sentence/paragraph boundaries when possible.
        """
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", ". ", " ", ""],
            length_function=len,
        )
        raw_chunks = splitter.split_text(text)
        return [
            ChunkData(text=t.strip(), chunk_index=i)
            for i, t in enumerate(raw_chunks)
            if t.strip()
        ]
