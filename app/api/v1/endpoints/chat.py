"""
Chat endpoints.

POST   /chat                            → send a message (orchestrated or direct)
GET    /chat/sessions/{session_id}      → get session history
GET    /chat/sessions                   → list user's sessions
"""
from __future__ import annotations

from fastapi import APIRouter, Query, status

from app.agents.graph.agent_graph_service import AgentGraphService, GraphChatInput
from app.core.dependencies import (
    AgentRepoDep,
    BedrockClientDep,
    ChatMessageRepoDep,
    ChatSessionRepoDep,
    EmbeddingClientDep,
    PineconeClientDep,
)
from app.core.exceptions import ChatSessionNotFoundError
from app.domain.entities.entities import ChatMessage, ChatSession
from app.schemas.chat_schemas import (
    AgentUsedResponse,
    ChatHistoryResponse,
    ChatMessageResponse,
    ChatRequest,
    ChatResponse,
    ChatSessionResponse,
    SourceResponse,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers: domain → schema
# ---------------------------------------------------------------------------

def _source_to_schema(s) -> SourceResponse:  # type: ignore[no-untyped-def]
    return SourceResponse(
        document_id=s.document_id,
        filename=s.filename,
        chunk_index=s.chunk_index,
        page_from=s.page_from,
        page_to=s.page_to,
        score=s.score,
    )


def _message_to_schema(msg: ChatMessage) -> ChatMessageResponse:
    return ChatMessageResponse(
        id=msg.id,
        session_id=msg.session_id,
        role=msg.role.value,
        content=msg.content,
        agent_id=msg.agent_id,
        agent_name=msg.agent_name,
        sources=[_source_to_schema(s) for s in msg.sources],
        prompt_tokens=msg.prompt_tokens,
        completion_tokens=msg.completion_tokens,
        created_at=msg.created_at,
    )


def _session_to_schema(session: ChatSession) -> ChatSessionResponse:
    return ChatSessionResponse(
        id=session.id,
        user_id=session.user_id,
        agent_id=session.agent_id,
        title=session.title,
        is_active=session.is_active,
        created_at=session.created_at,
        updated_at=session.updated_at,
    )


# ---------------------------------------------------------------------------
# POST /chat
# ---------------------------------------------------------------------------

@router.post(
    "",
    response_model=ChatResponse,
    status_code=status.HTTP_200_OK,
    summary="Send a message to the multi-agent platform",
    description=(
        "Routes the query to the appropriate specialized agent via LangGraph orchestration. "
        "If `agent_id` is provided, routing is bypassed and the query goes directly to that agent. "
        "Returns the AI answer plus the sources (documents + chunks) used to generate it."
    ),
)
async def chat(
    body: ChatRequest,
    agent_repo: AgentRepoDep,
    session_repo: ChatSessionRepoDep,
    message_repo: ChatMessageRepoDep,
    embedding_client: EmbeddingClientDep,
    pinecone_client: PineconeClientDep,
    bedrock_client: BedrockClientDep,
) -> ChatResponse:
    svc = AgentGraphService(
        agent_repo=agent_repo,
        session_repo=session_repo,
        message_repo=message_repo,
        embedding_client=embedding_client,
        pinecone_client=pinecone_client,
        bedrock_client=bedrock_client,
    )

    result = await svc.execute(
        GraphChatInput(
            user_id=body.user_id,
            message=body.message,
            session_id=body.session_id,
            agent_id=body.agent_id,
            tenant_id=body.tenant_id,
        )
    )

    agent_used = None
    if result.agent_used:
        agent_used = AgentUsedResponse(
            id=result.agent_used["id"],
            name=result.agent_used["name"],
            topic=result.agent_used["topic"],
        )

    return ChatResponse(
        message_id=result.message_id,
        session_id=result.session_id,
        answer=result.answer,
        agent_used=agent_used,
        sources=[_source_to_schema(s) for s in result.sources],
        prompt_tokens=result.prompt_tokens,
        completion_tokens=result.completion_tokens,
        routing_reason=result.routing_reason,
        error=result.error,
    )


# ---------------------------------------------------------------------------
# GET /chat/sessions/{session_id}
# ---------------------------------------------------------------------------

@router.get(
    "/sessions/{session_id}",
    response_model=ChatHistoryResponse,
    summary="Retrieve full conversation history for a session",
)
async def get_session_history(
    session_id: str,
    session_repo: ChatSessionRepoDep,
    message_repo: ChatMessageRepoDep,
) -> ChatHistoryResponse:
    session = await session_repo.get_by_id(session_id)
    if not session:
        raise ChatSessionNotFoundError(session_id)

    messages = await message_repo.list_by_session(session_id)

    return ChatHistoryResponse(
        session=_session_to_schema(session),
        messages=[_message_to_schema(m) for m in messages],
    )


# ---------------------------------------------------------------------------
# GET /chat/sessions
# ---------------------------------------------------------------------------

@router.get(
    "/sessions",
    response_model=list[ChatSessionResponse],
    summary="List all chat sessions for a user",
)
async def list_sessions(
    session_repo: ChatSessionRepoDep,
    user_id: str = Query(default="demo-user-id"),
) -> list[ChatSessionResponse]:
    sessions = await session_repo.list_by_user(user_id)
    return [_session_to_schema(s) for s in sessions]
