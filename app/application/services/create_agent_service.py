"""
CreateAgentService — creates a new specialized agent.

Business rules (from PROJECT_CONTEXT.md):
1. Save agent in PostgreSQL
2. Generate unique Pinecone namespace: tenant_{tid}_user{uid}_agent{aid}
3. Create associated KnowledgeBase record
4. DO NOT create a Pinecone index — only namespaces exist logically until first upsert
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from app.core.config import settings
from app.core.exceptions import AgentNotFoundError
from app.core.logging import get_logger
from app.domain.entities.entities import Agent, KnowledgeBase
from app.infrastructure.db.repositories.agent_repository import (
    AgentRepository,
    KnowledgeBaseRepository,
)

logger = get_logger(__name__)


@dataclass
class CreateAgentInput:
    user_id: str
    tenant_id: int
    name: str
    description: str
    topic: str
    system_prompt: str
    llm_model: Optional[str] = None
    llm_temperature: Optional[float] = None
    llm_max_tokens: Optional[int] = None
    embedding_model: Optional[str] = None


@dataclass
class CreateAgentOutput:
    agent: Agent
    knowledge_base: KnowledgeBase


class CreateAgentService:
    """
    Use case: create a new agent with its knowledge base record.
    """

    def __init__(
        self,
        agent_repo: AgentRepository,
        kb_repo: KnowledgeBaseRepository,
    ) -> None:
        self._agent_repo = agent_repo
        self._kb_repo = kb_repo

    async def execute(self, data: CreateAgentInput) -> CreateAgentOutput:
        agent_id = str(uuid.uuid4())

        # Build the canonical namespace
        namespace = (
            f"tenant_{data.tenant_id}_user{data.user_id}_agent{agent_id}"
        )

        agent = Agent(
            id=agent_id,
            user_id=data.user_id,
            tenant_id=data.tenant_id,
            name=data.name,
            description=data.description,
            topic=data.topic,
            system_prompt=data.system_prompt,
            pinecone_namespace=namespace,
            embedding_model=data.embedding_model or settings.google_embedding_model,
            llm_model=data.llm_model or settings.bedrock_default_model_id,
            llm_temperature=data.llm_temperature if data.llm_temperature is not None
                            else settings.bedrock_temperature,
            llm_max_tokens=data.llm_max_tokens or settings.bedrock_max_tokens,
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        created_agent = await self._agent_repo.create(agent)

        # Create the associated KnowledgeBase record
        kb = KnowledgeBase(
            id=str(uuid.uuid4()),
            agent_id=created_agent.id,
            pinecone_index=settings.pinecone_index_name,
            pinecone_namespace=namespace,
            embedding_model=created_agent.embedding_model,
            embedding_dimension=settings.embedding_dimension,
            status="active",
            total_documents=0,
            total_chunks=0,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        created_kb = await self._kb_repo.create(kb)

        logger.info(
            "Agent created",
            agent_id=created_agent.id,
            namespace=namespace,
            user_id=data.user_id,
        )

        return CreateAgentOutput(agent=created_agent, knowledge_base=created_kb)
