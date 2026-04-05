"""
Pinecone vector database client.

Uses 1 shared index with namespaces per agent.
Namespace format: tenant_{tenant_id}_user{user_id}_agent{agent_id}

NEVER create a separate index per agent — violates PROJECT_CONTEXT.md.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from pinecone import Pinecone, ServerlessSpec
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings
from app.core.exceptions import VectorUpsertError, VectorQueryError
from app.core.logging import get_logger

logger = get_logger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Data types
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class VectorRecord:
    """A single vector to be upserted into Pinecone."""
    id: str                         # unique vector ID (chunk_id)
    values: list[float]             # embedding vector
    metadata: dict[str, Any]        # stored alongside the vector


@dataclass
class QueryResult:
    """A single result from a Pinecone similarity query."""
    id: str
    score: float
    metadata: dict[str, Any]

    @property
    def text(self) -> str:
        return self.metadata.get("text", "")

    @property
    def document_id(self) -> str:
        return self.metadata.get("document_id", "")

    @property
    def filename(self) -> str:
        return self.metadata.get("filename", "")

    @property
    def chunk_index(self) -> int:
        return int(self.metadata.get("chunk_index", 0))

    @property
    def page_from(self) -> Optional[int]:
        v = self.metadata.get("page_from")
        return int(v) if v is not None else None

    @property
    def page_to(self) -> Optional[int]:
        v = self.metadata.get("page_to")
        return int(v) if v is not None else None


# ─────────────────────────────────────────────────────────────────────────────
# Client
# ─────────────────────────────────────────────────────────────────────────────

class PineconeClient:
    """
    Thin adapter around the Pinecone SDK.

    All operations target a SINGLE shared index.
    Namespace isolation is enforced per agent (from PROJECT_CONTEXT.md).

    Required Pinecone metadata fields per vector:
        chunk_id, document_id, agent_id, knowledge_base_id (optional),
        filename, text, chunk_index, page_from, page_to, created_at
    """

    _UPSERT_BATCH_SIZE = 100   # Pinecone recommends ≤ 100 vectors per upsert

    def __init__(
        self,
        api_key: Optional[str] = None,
        index_name: Optional[str] = None,
        dimension: Optional[int] = None,
        cloud: Optional[str] = None,
        region: Optional[str] = None,
    ) -> None:
        self._api_key = api_key or settings.pinecone_api_key
        self._index_name = index_name or settings.pinecone_index_name
        self._dimension = dimension or settings.embedding_dimension
        self._cloud = cloud or settings.pinecone_cloud
        self._region = region or settings.pinecone_region

        self._pc = Pinecone(api_key=self._api_key)
        self._index = self._get_or_create_index()

        logger.info(
            "PineconeClient initialized",
            index=self._index_name,
            dimension=self._dimension,
        )

    def _get_or_create_index(self):  # type: ignore[no-untyped-def]
        """
        Connect to existing index or create it if it doesn't exist.
        In production the index should be pre-created via IaC (Terraform, etc.).
        """
        existing = [idx.name for idx in self._pc.list_indexes()]
        if self._index_name not in existing:
            logger.info(
                "Creating Pinecone index",
                index=self._index_name,
                dimension=self._dimension,
            )
            self._pc.create_index(
                name=self._index_name,
                dimension=self._dimension,
                metric="cosine",
                spec=ServerlessSpec(cloud=self._cloud, region=self._region),
            )
        return self._pc.Index(self._index_name)

    @staticmethod
    def build_namespace(tenant_id: int, user_id: str, agent_id: str) -> str:
        """
        Generate the canonical Pinecone namespace for an agent.
        Format: tenant_{tenant_id}_user{user_id}_agent{agent_id}
        """
        return f"tenant_{tenant_id}_user{user_id}_agent{agent_id}"

    # ── Upsert ────────────────────────────────────────────────────────────────

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=15),
        reraise=True,
    )
    async def upsert(self, namespace: str, records: list[VectorRecord]) -> int:
        """
        Upsert vectors into the given namespace.
        Automatically batches into groups of _UPSERT_BATCH_SIZE.
        Returns total number of upserted vectors.
        """
        if not records:
            return 0

        try:
            total = 0
            for i in range(0, len(records), self._UPSERT_BATCH_SIZE):
                batch = records[i : i + self._UPSERT_BATCH_SIZE]
                vectors = [
                    {"id": r.id, "values": r.values, "metadata": r.metadata}
                    for r in batch
                ]
                self._index.upsert(vectors=vectors, namespace=namespace)
                total += len(batch)
                logger.debug(
                    "Pinecone upsert batch",
                    namespace=namespace,
                    batch_size=len(batch),
                    total_so_far=total,
                )

            logger.info(
                "Pinecone upsert complete",
                namespace=namespace,
                total_vectors=total,
            )
            return total

        except Exception as exc:
            logger.error("Pinecone upsert failed", namespace=namespace, error=str(exc))
            raise VectorUpsertError(detail=str(exc)) from exc

    # ── Query ─────────────────────────────────────────────────────────────────

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        reraise=True,
    )
    async def query(
        self,
        namespace: str,
        query_vector: list[float],
        top_k: int = 5,
        filter: Optional[dict[str, Any]] = None,
        min_score: float = 0.0,
    ) -> list[QueryResult]:
        """
        Query the namespace for the top_k most similar vectors.
        Optionally filter by metadata and/or minimum similarity score.
        """
        try:
            response = self._index.query(
                namespace=namespace,
                vector=query_vector,
                top_k=top_k,
                include_metadata=True,
                filter=filter or {},
            )
            results = [
                QueryResult(
                    id=match["id"],
                    score=match["score"],
                    metadata=match.get("metadata", {}),
                )
                for match in response.get("matches", [])
                if match["score"] >= min_score
            ]

            logger.debug(
                "Pinecone query complete",
                namespace=namespace,
                top_k=top_k,
                returned=len(results),
            )
            return results

        except Exception as exc:
            logger.error("Pinecone query failed", namespace=namespace, error=str(exc))
            raise VectorQueryError(detail=str(exc)) from exc

    # ── Delete ────────────────────────────────────────────────────────────────

    async def delete_by_ids(self, namespace: str, vector_ids: list[str]) -> None:
        """Delete specific vectors by ID from a namespace."""
        if not vector_ids:
            return
        try:
            self._index.delete(ids=vector_ids, namespace=namespace)
            logger.info(
                "Vectors deleted",
                namespace=namespace,
                count=len(vector_ids),
            )
        except Exception as exc:
            logger.error("Pinecone delete failed", error=str(exc))
            raise VectorUpsertError(detail=str(exc)) from exc

    async def delete_by_document(
        self, namespace: str, document_id: str
    ) -> None:
        """
        Delete all vectors belonging to a document.
        Uses metadata filter — requires Pinecone plan that supports filter-based delete.
        """
        try:
            self._index.delete(
                namespace=namespace,
                filter={"document_id": {"$eq": document_id}},
            )
            logger.info(
                "Vectors deleted by document",
                namespace=namespace,
                document_id=document_id,
            )
        except Exception as exc:
            logger.error(
                "Pinecone delete_by_document failed",
                document_id=document_id,
                error=str(exc),
            )
            raise VectorUpsertError(detail=str(exc)) from exc

    async def delete_namespace(self, namespace: str) -> None:
        """Delete all vectors in a namespace (e.g., when deleting an agent)."""
        try:
            self._index.delete(namespace=namespace, delete_all=True)
            logger.info("Namespace deleted", namespace=namespace)
        except Exception as exc:
            logger.error("Pinecone delete_namespace failed", error=str(exc))
            raise VectorUpsertError(detail=str(exc)) from exc

    # ── Stats ─────────────────────────────────────────────────────────────────

    async def describe_namespace(self, namespace: str) -> dict[str, Any]:
        """Return stats for a specific namespace."""
        try:
            stats = self._index.describe_index_stats()
            ns_stats = stats.get("namespaces", {}).get(namespace, {})
            return {
                "namespace": namespace,
                "vector_count": ns_stats.get("vector_count", 0),
            }
        except Exception as exc:
            logger.error("describe_namespace failed", namespace=namespace, error=str(exc))
            return {"namespace": namespace, "vector_count": 0}
