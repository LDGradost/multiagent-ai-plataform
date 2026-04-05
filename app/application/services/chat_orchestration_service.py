"""
ChatOrchestrationService — the main chat use case.

Two modes:
A) Direct: agent_id is provided → skip orchestrator, go straight to the agent's RAG
B) Orchestrated: no agent_id → orchestrator selects the best agent via Bedrock routing

Workflow (orchestrated):
1. Load active agents from PostgreSQL
2. Call BedrockClient.route() with system routing prompt + agent list
3. Parse routing decision → agent_id, UNCLEAR, or NONE
4. Run RAG: embed query → Pinecone search in agent namespace
5. Build final prompt with context
6. Call BedrockClient.invoke() for the answer
7. Persist ChatSession + ChatMessage (user + assistant) in PostgreSQL
8. Return ChatResponse with answer + sources
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from app.core.config import settings
from app.core.exceptions import (
    AgentNotFoundError,
    ChatSessionNotFoundError,
    NoAgentFoundError,
)
from app.core.logging import get_logger
from app.domain.entities.entities import (
    Agent,
    ChatMessage,
    ChatMessageRole,
    ChatSession,
    ChatSource,
)
from app.infrastructure.bedrock.bedrock_client import BedrockClient, BedrockMessage
from app.infrastructure.db.repositories.agent_repository import AgentRepository
from app.infrastructure.db.repositories.chat_repository import (
    ChatMessageRepository,
    ChatSessionRepository,
)
from app.infrastructure.embeddings.google_embedding_client import IEmbeddingClient
from app.infrastructure.pinecone.pinecone_client import PineconeClient

logger = get_logger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Prompts
# ─────────────────────────────────────────────────────────────────────────────

ORCHESTRATOR_SYSTEM_PROMPT = """You are an intelligent routing assistant.
Your ONLY job is to select which specialized agent should handle the user's query.

Available agents (JSON list):
{agents_json}

Rules:
- Reply with ONLY a JSON object: {{"agent_id": "<id>", "reason": "<brief reason>"}}
- If no agent is clearly relevant, reply: {{"agent_id": "NONE", "reason": "<why>"}}
- If the query is ambiguous, reply: {{"agent_id": "UNCLEAR", "reason": "<what is unclear>"}}
- Do NOT answer the user's question. Only route.
- Do NOT invent agent IDs. Use only the IDs from the list above.
"""

SPECIALIZED_AGENT_SYSTEM_PROMPT = """You are {agent_name}, a specialized assistant for: {agent_topic}.

{agent_system_prompt}

IMPORTANT RULES:
1. Answer ONLY based on the provided context below.
2. If the context does not contain enough information to answer, clearly say so.
3. Do NOT invent facts or make things up.
4. Always cite your sources by saying "According to [filename]..." when relevant.
5. Be concise and professional.

Context from knowledge base:
---
{context}
---
"""

NO_CONTEXT_MESSAGE = (
    "I could not find relevant information in the knowledge base to answer your question. "
    "Please refine your query or check if the relevant documents have been uploaded."
)

UNCLEAR_MESSAGE = (
    "Your question is ambiguous. Could you please clarify what area you are asking about? "
    "Available topics: {topics}"
)

NO_AGENT_MESSAGE = (
    "I could not find a specialized agent relevant to your question. "
    "Available agents cover: {topics}. Please rephrase or contact support."
)


# ─────────────────────────────────────────────────────────────────────────────
# DTOs
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ChatInput:
    user_id: str
    message: str
    session_id: Optional[str] = None
    agent_id: Optional[str] = None   # direct routing if provided
    tenant_id: int = 1


@dataclass
class ChatOutput:
    message_id: str
    session_id: str
    answer: str
    agent_used: Optional[dict]       # {id, name, topic}
    sources: list[ChatSource]
    prompt_tokens: int
    completion_tokens: int
    routing_reason: Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────
# Service
# ─────────────────────────────────────────────────────────────────────────────

class ChatOrchestrationService:
    """
    Main chat use case. Supports direct and orchestrated routing.
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

    async def execute(self, data: ChatInput) -> ChatOutput:
        # ── 1. Resolve or create session ──────────────────────────────────────
        session = await self._get_or_create_session(data)

        # ── 2. Persist user message ───────────────────────────────────────────
        await self._persist_message(
            session_id=session.id,
            role=ChatMessageRole.USER,
            content=data.message,
        )

        # ── 3. Select agent ───────────────────────────────────────────────────
        routing_reason: Optional[str] = None

        if data.agent_id:
            # Direct mode: user explicitly chose an agent
            agent = await self._agent_repo.get_by_id(data.agent_id)
            if not agent or not agent.is_active:
                raise AgentNotFoundError(data.agent_id)
            routing_reason = "Direct routing — agent_id provided by client"
            logger.info("Direct routing", agent_id=agent.id)
        else:
            # Orchestrated mode: route via Bedrock
            agent, routing_reason = await self._route_query(data.message)

        # ── 4. RAG: embed query + search Pinecone ─────────────────────────────
        query_vector = await self._embedding.embed_query(data.message)
        results = await self._pinecone.query(
            namespace=agent.pinecone_namespace,
            query_vector=query_vector,
            top_k=5,
            min_score=0.30,
        )

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

        # ── 5. Build context and system prompt ────────────────────────────────
        if results:
            context_text = "\n\n---\n\n".join(
                [f"[{r.filename} | chunk {r.chunk_index}]\n{r.text}" for r in results]
            )
        else:
            context_text = "No relevant information found."

        system_prompt = SPECIALIZED_AGENT_SYSTEM_PROMPT.format(
            agent_name=agent.name,
            agent_topic=agent.topic,
            agent_system_prompt=agent.system_prompt,
            context=context_text,
        )

        # ── 6. Generate answer with Bedrock ───────────────────────────────────
        if not results:
            answer = NO_CONTEXT_MESSAGE
            bedrock_response = None
        else:
            bedrock_response = await self._bedrock.invoke(
                messages=[BedrockMessage(role="user", content=data.message)],
                system_prompt=system_prompt,
                model_id=agent.llm_model,
                max_tokens=agent.llm_max_tokens,
                temperature=agent.llm_temperature,
            )
            answer = bedrock_response.content

        # ── 7. Persist assistant message ──────────────────────────────────────
        assistant_msg = await self._persist_message(
            session_id=session.id,
            role=ChatMessageRole.ASSISTANT,
            content=answer,
            agent_id=agent.id,
            agent_name=agent.name,
            sources=sources,
            prompt_tokens=bedrock_response.input_tokens if bedrock_response else 0,
            completion_tokens=bedrock_response.output_tokens if bedrock_response else 0,
        )

        logger.info(
            "Chat complete",
            session_id=session.id,
            agent_id=agent.id,
            sources_count=len(sources),
            answer_length=len(answer),
        )

        return ChatOutput(
            message_id=assistant_msg.id,
            session_id=session.id,
            answer=answer,
            agent_used={"id": agent.id, "name": agent.name, "topic": agent.topic},
            sources=sources,
            prompt_tokens=bedrock_response.input_tokens if bedrock_response else 0,
            completion_tokens=bedrock_response.output_tokens if bedrock_response else 0,
            routing_reason=routing_reason,
        )

    # ── Routing logic ─────────────────────────────────────────────────────────

    async def _route_query(self, message: str) -> tuple[Agent, str]:
        """
        Use Bedrock (lightweight model) to decide which agent should respond.
        Returns (agent, reason).
        Raises NoAgentFoundError or returns a clarification message.
        """
        active_agents = await self._agent_repo.list_all_active()
        if not active_agents:
            raise NoAgentFoundError()

        agents_json = json.dumps(
            [
                {
                    "agent_id": a.id,
                    "name": a.name,
                    "topic": a.topic,
                    "description": a.description,
                }
                for a in active_agents
            ],
            ensure_ascii=False,
            indent=2,
        )

        system_prompt = ORCHESTRATOR_SYSTEM_PROMPT.format(agents_json=agents_json)
        raw_response = await self._bedrock.route(
            user_message=message,
            system_prompt=system_prompt,
        )

        # Parse JSON routing decision
        try:
            # Strip markdown code fences if the model wrapped the JSON
            clean = raw_response.strip().strip("```json").strip("```").strip()
            decision = json.loads(clean)
            chosen_id = decision.get("agent_id", "NONE")
            reason = decision.get("reason", "")
        except (json.JSONDecodeError, KeyError):
            logger.warning("Could not parse routing response", raw=raw_response[:200])
            chosen_id = "NONE"
            reason = "Routing response was not valid JSON"

        topics = ", ".join(a.topic for a in active_agents)

        if chosen_id == "UNCLEAR":
            raise NoAgentFoundError()  # Caller can handle UNCLEAR separately

        if chosen_id == "NONE":
            raise NoAgentFoundError()

        # Find the agent
        agent = next((a for a in active_agents if a.id == chosen_id), None)
        if not agent:
            logger.error("Routing returned unknown agent_id", chosen_id=chosen_id)
            raise NoAgentFoundError()

        logger.info(
            "Orchestrator routing decision",
            chosen_agent_id=agent.id,
            chosen_agent=agent.name,
            reason=reason,
        )
        return agent, reason

    # ── Session helpers ───────────────────────────────────────────────────────

    async def _get_or_create_session(self, data: ChatInput) -> ChatSession:
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
