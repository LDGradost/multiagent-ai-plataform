"""
Agents endpoints — full CRUD for specialized agents.

POST   /agents              → create agent
GET    /agents              → list user's agents
GET    /agents/{agent_id}   → get agent detail
PATCH  /agents/{agent_id}   → update agent
DELETE /agents/{agent_id}   → deactivate agent
"""
from __future__ import annotations

from typing import Annotated, Optional
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, status

from app.application.services.create_agent_service import (
    CreateAgentInput,
    CreateAgentService,
)
from app.core.config import settings
from app.core.dependencies import (
    AgentRepoDep,
    KBRepoDep,
)
from app.core.exceptions import AgentNotFoundError
from app.schemas.agent_schemas import (
    AgentCreateRequest,
    AgentListResponse,
    AgentResponse,
    AgentUpdateRequest,
    KnowledgeBaseResponse,
)
from app.domain.entities.entities import Agent, KnowledgeBase

router = APIRouter()

# ---------------------------------------------------------------------------
# Helpers: domain → schema mappers
# ---------------------------------------------------------------------------

def _kb_to_schema(kb: KnowledgeBase) -> KnowledgeBaseResponse:
    return KnowledgeBaseResponse(
        id=kb.id,
        pinecone_index=kb.pinecone_index,
        pinecone_namespace=kb.pinecone_namespace,
        embedding_model=kb.embedding_model,
        embedding_dimension=kb.embedding_dimension,
        status=kb.status,
        total_documents=kb.total_documents,
        total_chunks=kb.total_chunks,
        created_at=kb.created_at,
    )


def _agent_to_schema(
    agent: Agent, kb: Optional[KnowledgeBase] = None
) -> AgentResponse:
    return AgentResponse(
        id=agent.id,
        user_id=agent.user_id,
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
        created_at=agent.created_at,
        updated_at=agent.updated_at,
        knowledge_base=_kb_to_schema(kb) if kb else None,
    )


# ---------------------------------------------------------------------------
# POST /agents
# ---------------------------------------------------------------------------

@router.post(
    "",
    response_model=AgentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new specialized agent",
    description=(
        "Creates a new agent with its associated Pinecone namespace and knowledge base. "
        "The namespace format is: `tenant_{tenant_id}_user{user_id}_agent{agent_id}`. "
        "No Pinecone index is created here — only a logical namespace."
    ),
)
async def create_agent(
    body: AgentCreateRequest,
    agent_repo: AgentRepoDep,
    kb_repo: KBRepoDep,
    # In a real app, user_id comes from JWT token. Hardcoded here for simplicity.
    user_id: str = Query(default="demo-user-id", description="Authenticated user ID"),
    tenant_id: int = Query(default=1, description="Tenant ID"),
) -> AgentResponse:
    svc = CreateAgentService(agent_repo=agent_repo, kb_repo=kb_repo)
    result = await svc.execute(
        CreateAgentInput(
            user_id=user_id,
            tenant_id=tenant_id,
            name=body.name,
            description=body.description,
            topic=body.topic,
            system_prompt=body.system_prompt,
            llm_model=body.llm_model,
            llm_temperature=body.llm_temperature,
            llm_max_tokens=body.llm_max_tokens,
            embedding_model=body.embedding_model,
        )
    )
    return _agent_to_schema(result.agent, result.knowledge_base)


# ---------------------------------------------------------------------------
# GET /agents
# ---------------------------------------------------------------------------

@router.get(
    "",
    response_model=AgentListResponse,
    summary="List all agents for the authenticated user",
)
async def list_agents(
    agent_repo: AgentRepoDep,
    kb_repo: KBRepoDep,
    user_id: str = Query(default="demo-user-id"),
    active_only: bool = Query(default=True),
) -> AgentListResponse:
    agents = await agent_repo.list_by_user(user_id=user_id, active_only=active_only)

    agent_responses = []
    for agent in agents:
        kb = await kb_repo.get_by_agent_id(agent.id)
        agent_responses.append(_agent_to_schema(agent, kb))

    return AgentListResponse(total=len(agent_responses), agents=agent_responses)


# ---------------------------------------------------------------------------
# GET /agents/{agent_id}
# ---------------------------------------------------------------------------

@router.get(
    "/{agent_id}",
    response_model=AgentResponse,
    summary="Get agent details including knowledge base stats",
)
async def get_agent(
    agent_id: str,
    agent_repo: AgentRepoDep,
    kb_repo: KBRepoDep,
) -> AgentResponse:
    agent = await agent_repo.get_by_id(agent_id)
    if not agent:
        raise AgentNotFoundError(agent_id)
    kb = await kb_repo.get_by_agent_id(agent_id)
    return _agent_to_schema(agent, kb)


# ---------------------------------------------------------------------------
# PATCH /agents/{agent_id}
# ---------------------------------------------------------------------------

@router.patch(
    "/{agent_id}",
    response_model=AgentResponse,
    summary="Update agent configuration",
)
async def update_agent(
    agent_id: str,
    body: AgentUpdateRequest,
    agent_repo: AgentRepoDep,
    kb_repo: KBRepoDep,
) -> AgentResponse:
    agent = await agent_repo.get_by_id(agent_id)
    if not agent:
        raise AgentNotFoundError(agent_id)

    # Apply partial updates
    updated = Agent(
        id=agent.id,
        user_id=agent.user_id,
        tenant_id=agent.tenant_id,
        name=body.name if body.name is not None else agent.name,
        description=body.description if body.description is not None else agent.description,
        topic=body.topic if body.topic is not None else agent.topic,
        system_prompt=body.system_prompt if body.system_prompt is not None else agent.system_prompt,
        pinecone_namespace=agent.pinecone_namespace,
        embedding_model=agent.embedding_model,
        llm_model=body.llm_model if body.llm_model is not None else agent.llm_model,
        llm_temperature=body.llm_temperature if body.llm_temperature is not None else agent.llm_temperature,
        llm_max_tokens=body.llm_max_tokens if body.llm_max_tokens is not None else agent.llm_max_tokens,
        is_active=body.is_active if body.is_active is not None else agent.is_active,
        created_at=agent.created_at,
        updated_at=datetime.now(timezone.utc),
    )
    saved = await agent_repo.update(updated)
    kb = await kb_repo.get_by_agent_id(agent_id)
    return _agent_to_schema(saved, kb)


# ---------------------------------------------------------------------------
# DELETE /agents/{agent_id}  (soft delete — sets is_active=False)
# ---------------------------------------------------------------------------

@router.delete(
    "/{agent_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Deactivate an agent (soft delete)",
)
async def delete_agent(
    agent_id: str,
    agent_repo: AgentRepoDep,
) -> None:
    agent = await agent_repo.get_by_id(agent_id)
    if not agent:
        raise AgentNotFoundError(agent_id)
    agent.is_active = False
    await agent_repo.update(agent)
