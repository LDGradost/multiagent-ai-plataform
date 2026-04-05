"""
SearchKnowledgeService — semantic search within an agent's namespace.

Workflow:
1. Embed the user query with the same model used for indexing
2. Query Pinecone restricted to the agent's namespace
3. Return ranked QueryResult list with text and metadata

This service is used by ChatOrchestrationService and can also be
called independently for retrieval-only use cases.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.core.exceptions import AgentNotFoundError
from app.core.logging import get_logger
from app.domain.entities.entities import Agent, ChatSource
from app.infrastructure.db.repositories.agent_repository import AgentRepository
from app.infrastructure.embeddings.google_embedding_client import IEmbeddingClient
from app.infrastructure.pinecone.pinecone_client import PineconeClient, QueryResult

logger = get_logger(__name__)


@dataclass
class SearchInput:
    query: str
    agent_id: str
    top_k: int = 5
    min_score: float = 0.3
    filter: Optional[dict] = None


@dataclass
class SearchOutput:
    results: list[QueryResult]
    sources: list[ChatSource]
    agent: Agent
    query_used: str


class SearchKnowledgeService:
    """
    Use case: embed a query and retrieve relevant chunks from an agent's namespace.
    """

    def __init__(
        self,
        agent_repo: AgentRepository,
        embedding_client: IEmbeddingClient,
        pinecone_client: PineconeClient,
    ) -> None:
        self._agent_repo = agent_repo
        self._embedding = embedding_client
        self._pinecone = pinecone_client

    async def execute(self, data: SearchInput) -> SearchOutput:
        # ── 1. Validate agent ─────────────────────────────────────────────────
        agent = await self._agent_repo.get_by_id(data.agent_id)
        if not agent or not agent.is_active:
            raise AgentNotFoundError(data.agent_id)

        # ── 2. Embed query ────────────────────────────────────────────────────
        query_vector = await self._embedding.embed_query(data.query)

        logger.debug(
            "Query embedded",
            agent_id=data.agent_id,
            namespace=agent.pinecone_namespace,
            top_k=data.top_k,
        )

        # ── 3. Query Pinecone — ONLY the agent's namespace ────────────────────
        results = await self._pinecone.query(
            namespace=agent.pinecone_namespace,
            query_vector=query_vector,
            top_k=data.top_k,
            filter=data.filter,
            min_score=data.min_score,
        )

        # ── 4. Map to ChatSource for API response ────────────────────────────
        sources = [
            ChatSource(
                document_id=r.document_id,
                filename=r.filename,
                chunk_index=r.chunk_index,
                page_from=r.page_from,
                page_to=r.page_to,
                score=round(r.score, 4),
            )
            for r in results
        ]

        logger.info(
            "Search complete",
            agent_id=data.agent_id,
            results_returned=len(results),
            top_score=results[0].score if results else None,
        )

        return SearchOutput(
            results=results,
            sources=sources,
            agent=agent,
            query_used=data.query,
        )
