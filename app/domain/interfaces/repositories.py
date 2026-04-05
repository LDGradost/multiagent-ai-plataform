"""
Abstract repository interfaces (ports).
Infrastructure implementations must satisfy these contracts.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from app.domain.entities.entities import (
    Agent,
    Document,
    DocumentChunk,
    KnowledgeBase,
    ChatSession,
    ChatMessage,
    User,
)


class IAgentRepository(ABC):
    @abstractmethod
    async def create(self, agent: Agent) -> Agent: ...

    @abstractmethod
    async def get_by_id(self, agent_id: str) -> Optional[Agent]: ...

    @abstractmethod
    async def list_by_user(
        self, user_id: str, active_only: bool = True
    ) -> list[Agent]: ...

    @abstractmethod
    async def update(self, agent: Agent) -> Agent: ...

    @abstractmethod
    async def delete(self, agent_id: str) -> None: ...

    @abstractmethod
    async def list_all_active(self) -> list[Agent]: ...


class IKnowledgeBaseRepository(ABC):
    @abstractmethod
    async def create(self, kb: KnowledgeBase) -> KnowledgeBase: ...

    @abstractmethod
    async def get_by_agent_id(self, agent_id: str) -> Optional[KnowledgeBase]: ...

    @abstractmethod
    async def update_counts(
        self, kb_id: str, documents_delta: int, chunks_delta: int
    ) -> None: ...


class IDocumentRepository(ABC):
    @abstractmethod
    async def create(self, document: Document) -> Document: ...

    @abstractmethod
    async def get_by_id(self, document_id: str) -> Optional[Document]: ...

    @abstractmethod
    async def list_by_agent(self, agent_id: str) -> list[Document]: ...

    @abstractmethod
    async def update_status(
        self,
        document_id: str,
        status: str,
        error_message: Optional[str] = None,
    ) -> None: ...

    @abstractmethod
    async def update_after_processing(
        self,
        document_id: str,
        total_chunks: int,
        embedding_model: str,
    ) -> None: ...

    @abstractmethod
    async def delete(self, document_id: str) -> None: ...


class IDocumentChunkRepository(ABC):
    @abstractmethod
    async def bulk_create(self, chunks: list[DocumentChunk]) -> None: ...

    @abstractmethod
    async def list_by_document(self, document_id: str) -> list[DocumentChunk]: ...

    @abstractmethod
    async def delete_by_document(self, document_id: str) -> None: ...


class IChatSessionRepository(ABC):
    @abstractmethod
    async def create(self, session: ChatSession) -> ChatSession: ...

    @abstractmethod
    async def get_by_id(self, session_id: str) -> Optional[ChatSession]: ...

    @abstractmethod
    async def list_by_user(self, user_id: str) -> list[ChatSession]: ...


class IChatMessageRepository(ABC):
    @abstractmethod
    async def create(self, message: ChatMessage) -> ChatMessage: ...

    @abstractmethod
    async def list_by_session(self, session_id: str) -> list[ChatMessage]: ...


class IUserRepository(ABC):
    @abstractmethod
    async def get_by_id(self, user_id: str) -> Optional[User]: ...

    @abstractmethod
    async def get_by_email(self, email: str) -> Optional[User]: ...

    @abstractmethod
    async def create(self, user: User) -> User: ...
