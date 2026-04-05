"""
SQLAlchemy implementation of IAgentRepository and IKnowledgeBaseRepository.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.entities import Agent, KnowledgeBase
from app.domain.interfaces.repositories import IAgentRepository, IKnowledgeBaseRepository
from app.infrastructure.db.models.models import AgentModel, KnowledgeBaseModel


def _model_to_agent(m: AgentModel) -> Agent:
    return Agent(
        id=m.id,
        user_id=m.user_id,
        tenant_id=m.tenant_id,
        name=m.name,
        description=m.description,
        topic=m.topic,
        system_prompt=m.system_prompt,
        pinecone_namespace=m.pinecone_namespace,
        embedding_model=m.embedding_model,
        llm_model=m.llm_model,
        llm_temperature=m.llm_temperature,
        llm_max_tokens=m.llm_max_tokens,
        is_active=m.is_active,
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


def _model_to_kb(m: KnowledgeBaseModel) -> KnowledgeBase:
    return KnowledgeBase(
        id=m.id,
        agent_id=m.agent_id,
        pinecone_index=m.pinecone_index,
        pinecone_namespace=m.pinecone_namespace,
        embedding_model=m.embedding_model,
        embedding_dimension=m.embedding_dimension,
        status=m.status.value,
        total_documents=m.total_documents,
        total_chunks=m.total_chunks,
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


class AgentRepository(IAgentRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, agent: Agent) -> Agent:
        model = AgentModel(
            id=agent.id,
            user_id=agent.user_id,
            tenant_id=agent.tenant_id,
            name=agent.name,
            description=agent.description,
            topic=agent.topic,
            system_prompt=agent.system_prompt,
            pinecone_namespace=agent.pinecone_namespace,
            embedding_model=agent.embedding_model,
            llm_model=agent.llm_model,
            llm_temperature=agent.llm_temperature,
            llm_max_tokens=agent.llm_max_tokens,
            is_active=agent.is_active,
        )
        self._session.add(model)
        await self._session.flush()
        return _model_to_agent(model)

    async def get_by_id(self, agent_id: str) -> Optional[Agent]:
        result = await self._session.execute(
            select(AgentModel).where(AgentModel.id == agent_id)
        )
        model = result.scalar_one_or_none()
        return _model_to_agent(model) if model else None

    async def list_by_user(self, user_id: str, active_only: bool = True) -> list[Agent]:
        q = select(AgentModel).where(AgentModel.user_id == user_id)
        if active_only:
            q = q.where(AgentModel.is_active == True)  # noqa: E712
        q = q.order_by(AgentModel.created_at.desc())
        result = await self._session.execute(q)
        return [_model_to_agent(m) for m in result.scalars().all()]

    async def list_all_active(self) -> list[Agent]:
        result = await self._session.execute(
            select(AgentModel)
            .where(AgentModel.is_active == True)  # noqa: E712
            .order_by(AgentModel.name)
        )
        return [_model_to_agent(m) for m in result.scalars().all()]

    async def update(self, agent: Agent) -> Agent:
        await self._session.execute(
            update(AgentModel)
            .where(AgentModel.id == agent.id)
            .values(
                name=agent.name,
                description=agent.description,
                topic=agent.topic,
                system_prompt=agent.system_prompt,
                llm_model=agent.llm_model,
                llm_temperature=agent.llm_temperature,
                llm_max_tokens=agent.llm_max_tokens,
                is_active=agent.is_active,
                updated_at=datetime.now(timezone.utc),
            )
        )
        updated = await self.get_by_id(agent.id)
        assert updated is not None
        return updated

    async def delete(self, agent_id: str) -> None:
        result = await self._session.execute(
            select(AgentModel).where(AgentModel.id == agent_id)
        )
        model = result.scalar_one_or_none()
        if model:
            await self._session.delete(model)
            await self._session.flush()


class KnowledgeBaseRepository(IKnowledgeBaseRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, kb: KnowledgeBase) -> KnowledgeBase:
        model = KnowledgeBaseModel(
            id=kb.id,
            agent_id=kb.agent_id,
            pinecone_index=kb.pinecone_index,
            pinecone_namespace=kb.pinecone_namespace,
            embedding_model=kb.embedding_model,
            embedding_dimension=kb.embedding_dimension,
        )
        self._session.add(model)
        await self._session.flush()
        return _model_to_kb(model)

    async def get_by_agent_id(self, agent_id: str) -> Optional[KnowledgeBase]:
        result = await self._session.execute(
            select(KnowledgeBaseModel).where(KnowledgeBaseModel.agent_id == agent_id)
        )
        model = result.scalar_one_or_none()
        return _model_to_kb(model) if model else None

    async def update_counts(
        self, kb_id: str, documents_delta: int, chunks_delta: int
    ) -> None:
        result = await self._session.execute(
            select(KnowledgeBaseModel).where(KnowledgeBaseModel.id == kb_id)
        )
        model = result.scalar_one_or_none()
        if model:
            model.total_documents = max(0, model.total_documents + documents_delta)
            model.total_chunks = max(0, model.total_chunks + chunks_delta)
            await self._session.flush()
