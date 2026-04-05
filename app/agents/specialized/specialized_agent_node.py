"""
SpecializedAgentNode — a single LangGraph node that performs RAG for one agent.

Each active agent gets one of these nodes in the graph.
The node is created DYNAMICALLY from database data — no hardcoded agents.

LangChain role: constructs the RAG chain (retrieve → format → generate).
LangGraph role: updates state with the generated answer and sources.
"""
from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage

from app.agents.graph.state import AgentState
from app.agents.graph.prompts import (
    SPECIALIZED_AGENT_SYSTEM_PROMPT,
    NO_CONTEXT_ANSWER,
)
from app.core.logging import get_logger
from app.domain.entities.entities import Agent, ChatSource
from app.infrastructure.bedrock.bedrock_client import BedrockClient, BedrockMessage
from app.infrastructure.embeddings.google_embedding_client import IEmbeddingClient
from app.infrastructure.pinecone.pinecone_client import PineconeClient

logger = get_logger(__name__)


class SpecializedAgentNode:
    """
    LangGraph node for a specific specialized agent.

    Responsibilities:
    1. Embed the user query (RETRIEVAL_QUERY task type)
    2. Query Pinecone in the agent's namespace ONLY
    3. Build context from retrieved chunks
    4. Format prompt using agent's system_prompt
    5. Call Bedrock for generation
    6. Return state update with answer + sources
    """

    def __init__(
        self,
        agent: Agent,
        embedding_client: IEmbeddingClient,
        pinecone_client: PineconeClient,
        bedrock_client: BedrockClient,
        top_k: int = 5,
        min_score: float = 0.30,
    ) -> None:
        self._agent = agent
        self._embedding = embedding_client
        self._pinecone = pinecone_client
        self._bedrock = bedrock_client
        self._top_k = top_k
        self._min_score = min_score

    @property
    def agent_id(self) -> str:
        return self._agent.id

    async def __call__(self, state: AgentState) -> dict[str, Any]:
        query = state["user_query"]
        agent = self._agent

        logger.info(
            "SpecializedAgentNode invoked",
            agent_id=agent.id,
            agent_name=agent.name,
            namespace=agent.pinecone_namespace,
        )

        # ── 1. Embed query ────────────────────────────────────────────────────
        query_vector = await self._embedding.embed_query(query)

        # ── 2. Retrieve from Pinecone (namespace-isolated) ────────────────────
        results = await self._pinecone.query(
            namespace=agent.pinecone_namespace,
            query_vector=query_vector,
            top_k=self._top_k,
            min_score=self._min_score,
        )

        # ── 3. Map to sources ─────────────────────────────────────────────────
        sources: list[ChatSource] = [
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

        # ── 4. Build context string ───────────────────────────────────────────
        if results:
            context_blocks = [
                f"[Source: {r.filename} | Chunk {r.chunk_index}]\n{r.text}"
                for r in results
            ]
            context = "\n\n---\n\n".join(context_blocks)
        else:
            context = "No relevant information found in the knowledge base."

        # ── 5. Format system prompt ───────────────────────────────────────────
        system_prompt = SPECIALIZED_AGENT_SYSTEM_PROMPT.format(
            agent_name=agent.name,
            agent_topic=agent.topic,
            agent_custom_instructions=agent.system_prompt,
            context=context,
        )

        # ── 6. Generate answer with Bedrock ───────────────────────────────────
        if not results:
            answer = NO_CONTEXT_ANSWER
            prompt_tokens = 0
            completion_tokens = 0
        else:
            bedrock_response = await self._bedrock.invoke(
                messages=[BedrockMessage(role="user", content=query)],
                system_prompt=system_prompt,
                model_id=agent.llm_model,
                max_tokens=agent.llm_max_tokens,
                temperature=agent.llm_temperature,
            )
            answer = bedrock_response.content
            prompt_tokens = bedrock_response.input_tokens
            completion_tokens = bedrock_response.output_tokens

        logger.info(
            "SpecializedAgentNode complete",
            agent_id=agent.id,
            sources=len(sources),
            answer_length=len(answer),
        )

        # Return state update — LangGraph merges this into state
        return {
            "final_answer": answer,
            "context_chunks": results,
            "sources": sources,
            "selected_agent": agent,
            "prompt_tokens": prompt_tokens if results else 0,
            "completion_tokens": completion_tokens if results else 0,
            "messages": [AIMessage(content=answer)],
        }
