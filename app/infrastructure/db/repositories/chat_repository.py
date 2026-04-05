"""
SQLAlchemy implementation of IChatSessionRepository and IChatMessageRepository.
"""
from __future__ import annotations

import json
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.entities import (
    ChatMessage,
    ChatMessageRole,
    ChatSession,
    ChatSource,
)
from app.domain.interfaces.repositories import (
    IChatMessageRepository,
    IChatSessionRepository,
)
from app.infrastructure.db.models.models import ChatMessageModel, ChatSessionModel


def _model_to_session(m: ChatSessionModel) -> ChatSession:
    return ChatSession(
        id=m.id,
        user_id=m.user_id,
        agent_id=m.agent_id,
        title=m.title,
        is_active=m.is_active,
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


def _model_to_message(m: ChatMessageModel) -> ChatMessage:
    sources: list[ChatSource] = []
    if m.sources_json:
        raw = m.sources_json if isinstance(m.sources_json, list) else []
        sources = [
            ChatSource(
                document_id=s.get("document_id", ""),
                filename=s.get("filename", ""),
                chunk_index=s.get("chunk_index", 0),
                page_from=s.get("page_from"),
                page_to=s.get("page_to"),
                score=s.get("score", 0.0),
            )
            for s in raw
        ]
    return ChatMessage(
        id=m.id,
        session_id=m.session_id,
        role=ChatMessageRole(m.role),
        content=m.content,
        agent_id=m.agent_id,
        agent_name=m.agent_name,
        sources=sources,
        prompt_tokens=m.prompt_tokens,
        completion_tokens=m.completion_tokens,
        created_at=m.created_at,
    )


class ChatSessionRepository(IChatSessionRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, chat_session: ChatSession) -> ChatSession:
        model = ChatSessionModel(
            id=chat_session.id,
            user_id=chat_session.user_id,
            agent_id=chat_session.agent_id,
            title=chat_session.title,
            is_active=chat_session.is_active,
        )
        self._session.add(model)
        await self._session.flush()
        return _model_to_session(model)

    async def get_by_id(self, session_id: str) -> Optional[ChatSession]:
        result = await self._session.execute(
            select(ChatSessionModel).where(ChatSessionModel.id == session_id)
        )
        model = result.scalar_one_or_none()
        return _model_to_session(model) if model else None

    async def list_by_user(self, user_id: str) -> list[ChatSession]:
        result = await self._session.execute(
            select(ChatSessionModel)
            .where(ChatSessionModel.user_id == user_id)
            .order_by(ChatSessionModel.updated_at.desc())
        )
        return [_model_to_session(m) for m in result.scalars().all()]


class ChatMessageRepository(IChatMessageRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, message: ChatMessage) -> ChatMessage:
        sources_list = [
            {
                "document_id": s.document_id,
                "filename": s.filename,
                "chunk_index": s.chunk_index,
                "page_from": s.page_from,
                "page_to": s.page_to,
                "score": s.score,
            }
            for s in message.sources
        ]
        model = ChatMessageModel(
            id=message.id,
            session_id=message.session_id,
            role=message.role.value,
            content=message.content,
            agent_id=message.agent_id,
            agent_name=message.agent_name,
            sources_json=sources_list if sources_list else None,
            prompt_tokens=message.prompt_tokens,
            completion_tokens=message.completion_tokens,
        )
        self._session.add(model)
        await self._session.flush()
        return _model_to_message(model)

    async def list_by_session(self, session_id: str) -> list[ChatMessage]:
        result = await self._session.execute(
            select(ChatMessageModel)
            .where(ChatMessageModel.session_id == session_id)
            .order_by(ChatMessageModel.created_at)
        )
        return [_model_to_message(m) for m in result.scalars().all()]
