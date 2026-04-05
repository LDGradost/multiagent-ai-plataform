"""
AgentGraphService — facade that bridges FastAPI ↔ LangGraph.

Responsibilities:
1. Build the OrchestratorGraph at startup (or on demand per request)
2. Invoke the graph for a user query
3. Persist the conversation to PostgreSQL (ChatSession + ChatMessages)
4. Return a structured ChatOutput back to the API layer

Why a separate service instead of using ChatOrchestrationService?
- ChatOrchestrationService uses a direct Python call chain (Phases 5 approach)
- AgentGraphService uses LangGraph's StateGraph (Phase 6 approach)
- Both are provided so developers can choose the routing strategy
- In production, pick ONE. The API endpoints use AgentGraphService by default.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from app.agents.graph.orchestrator_graph import OrchestratorGraph
from app.agents.orchestrator.supervisor_node import SupervisorNode
from app.core.exceptions import NoAgentFoundError
from app.core.logging import get_logger
from app.domain.entities.entities import (
    ChatMessage,
    ChatMessageRole,
    ChatSession,
    ChatSource,
)
from app.infrastructure.bedrock.bedrock_client import BedrockClient
from app.infrastructure.db.repositories.agent_repository import AgentRepository
from app.infrastructure.db.repositories.chat_repository import (
    ChatMessageRepository,
    ChatSessionRepository,
)
from app.infrastructure.embeddings.google_embedding_client import IEmbeddingClient
from app.infrastructure.pinecone.pinecone_client import PineconeClient

logger = get_logger(__name__)


@dataclass
class GraphChatInput:
    user_id: str
    message: str
    session_id: Optional[str] = None
    agent_id: Optional[str] = None
    tenant_id: int = 1


@dataclass
class GraphChatOutput:
    message_id: str
    session_id: str
    answer: str
    agent_used: Optional[dict]
    sources: list[ChatSource]
    prompt_tokens: int
    completion_tokens: int
    routing_reason: Optional[str]
    error: Optional[str]


class AgentGraphService:
    """
    Facade service: builds and invokes the LangGraph orchestration,
    then handles session/message persistence.
    """

    def __init__(
        self,
        agent_repo: AgentRepository,
        session_repo: ChatSessionRepository,
        message_repo: ChatMessageRepository,
        embedding_client: IEmbeddingClient,
        pinecone_client: PineconeClient,
        bedrock_client: BedrockClient,
    ) -> None:
        self._agent_repo = agent_repo
        self._session_repo = session_repo
        self._message_repo = message_repo
        self._embedding = embedding_client
        self._pinecone = pinecone_client
        self._bedrock = bedrock_client

    async def _build_graph(self) -> OrchestratorGraph:
        """
        Build the graph with currently active agents.

        In production, consider caching this per-process and rebuilding
        only when agents are added/removed (via a cache invalidation event).
        """
        active_agents = await self._agent_repo.list_all_active()

        supervisor = SupervisorNode(
            agent_repo=self._agent_repo,
            bedrock_client=self._bedrock,
        )

        return OrchestratorGraph(
            agents=active_agents,
            supervisor_node=supervisor,
            embedding_client=self._embedding,
            pinecone_client=self._pinecone,
            bedrock_client=self._bedrock,
        )

    async def execute(self, data: GraphChatInput) -> GraphChatOutput:
        # ── 1. Resolve or create session ──────────────────────────────────────
        session = await self._get_or_create_session(data)

        # ── 2. Persist user message ───────────────────────────────────────────
        await self._persist_message(
            session_id=session.id,
            role=ChatMessageRole.USER,
            content=data.message,
        )

        # ── 3. Build and invoke graph ─────────────────────────────────────────
        graph = await self._build_graph()
        final_state = await graph.invoke(
            user_query=data.message,
            user_id=data.user_id,
            session_id=session.id,
            agent_id=data.agent_id,
            tenant_id=data.tenant_id,
        )

        # ── 4. Extract results from final state ───────────────────────────────
        answer = final_state.get("final_answer") or "No answer could be generated."
        sources: list[ChatSource] = final_state.get("sources", [])
        selected_agent = final_state.get("selected_agent")
        routing_reason = final_state.get("routing_reason")
        prompt_tokens = final_state.get("prompt_tokens", 0)
        completion_tokens = final_state.get("completion_tokens", 0)
        error = final_state.get("error")

        # Handle failure states
        if error in ("NO_AGENT_FOUND", "UNCLEAR_QUERY", "NO_AGENTS"):
            logger.warning("Graph ended with error", error=error)

        # ── 5. Persist assistant message ──────────────────────────────────────
        assistant_msg = await self._persist_message(
            session_id=session.id,
            role=ChatMessageRole.ASSISTANT,
            content=answer,
            agent_id=selected_agent.id if selected_agent else None,
            agent_name=selected_agent.name if selected_agent else None,
            sources=sources,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )

        logger.info(
            "AgentGraphService complete",
            session_id=session.id,
            agent_used=selected_agent.name if selected_agent else None,
            sources_count=len(sources),
        )

        return GraphChatOutput(
            message_id=assistant_msg.id,
            session_id=session.id,
            answer=answer,
            agent_used=(
                {
                    "id": selected_agent.id,
                    "name": selected_agent.name,
                    "topic": selected_agent.topic,
                }
                if selected_agent
                else None
            ),
            sources=sources,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            routing_reason=routing_reason,
            error=error,
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    async def _get_or_create_session(self, data: GraphChatInput) -> ChatSession:
        from app.core.exceptions import ChatSessionNotFoundError

        if data.session_id:
            session = await self._session_repo.get_by_id(data.session_id)
            if not session:
                raise ChatSessionNotFoundError(data.session_id)
            return session

        new_session = ChatSession(
            id=str(uuid.uuid4()),
            user_id=data.user_id,
            agent_id=data.agent_id,
            title=data.message[:60] + ("..." if len(data.message) > 60 else ""),
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        return await self._session_repo.create(new_session)

    async def _persist_message(
        self,
        session_id: str,
        role: ChatMessageRole,
        content: str,
        agent_id: Optional[str] = None,
        agent_name: Optional[str] = None,
        sources: Optional[list[ChatSource]] = None,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
    ) -> ChatMessage:
        msg = ChatMessage(
            id=str(uuid.uuid4()),
            session_id=session_id,
            role=role,
            content=content,
            agent_id=agent_id,
            agent_name=agent_name,
            sources=sources or [],
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            created_at=datetime.now(timezone.utc),
        )
        return await self._message_repo.create(msg)
