"""
OrchestratorGraph — the main LangGraph StateGraph.

Architecture:
  START → supervisor_node
              │
              ├─ agent_id found  → specialized_agent_node_{agent_id}
              ├─ "NONE"          → no_agent_node (reply that no agent was found)
              └─ "UNCLEAR"       → unclear_node (ask for clarification)
              │
              └─ END

Dynamic agent nodes:
  When the graph is compiled, it queries PostgreSQL for all active agents
  and adds one SpecializedAgentNode per agent. Adding a new agent in the DB
  automatically makes it available without restarting the graph.

LangChain role: BaseMessage handling, prompt formatting inside each node.
LangGraph role: StateGraph, conditional edges, state accumulation.
"""
from __future__ import annotations

import json
from typing import Any, Literal

from langchain_core.messages import HumanMessage
from langgraph.graph import StateGraph, END, START

from app.agents.graph.state import AgentState
from app.agents.graph.prompts import (
    NO_AGENT_ANSWER,
    UNCLEAR_ROUTING_ANSWER,
)
from app.agents.orchestrator.supervisor_node import SupervisorNode
from app.agents.specialized.specialized_agent_node import SpecializedAgentNode
from app.core.logging import get_logger
from app.domain.entities.entities import Agent
from app.infrastructure.bedrock.bedrock_client import BedrockClient
from app.infrastructure.db.repositories.agent_repository import AgentRepository
from app.infrastructure.embeddings.google_embedding_client import IEmbeddingClient
from app.infrastructure.pinecone.pinecone_client import PineconeClient

logger = get_logger(__name__)

# Reserved node names
NODE_SUPERVISOR = "supervisor"
NODE_NO_AGENT = "no_agent"
NODE_UNCLEAR = "unclear"


# ─────────────────────────────────────────────────────────────────────────────
# Terminal nodes (no routing, just update state)
# ─────────────────────────────────────────────────────────────────────────────

async def no_agent_node(state: AgentState) -> dict[str, Any]:
    """Terminal node: no suitable agent was found."""
    active_agents = state.get("context_chunks", [])
    answer = NO_AGENT_ANSWER.format(topics="various domains")
    logger.info("NoAgentNode: no suitable agent found")
    return {
        "final_answer": answer,
        "sources": [],
        "error": "NO_AGENT_FOUND",
    }


async def unclear_node(state: AgentState) -> dict[str, Any]:
    """Terminal node: query was too ambiguous to route."""
    answer = UNCLEAR_ROUTING_ANSWER.format(topics="various domains")
    logger.info("UnclearNode: ambiguous query")
    return {
        "final_answer": answer,
        "sources": [],
        "error": "UNCLEAR_QUERY",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Conditional edge router
# ─────────────────────────────────────────────────────────────────────────────

def route_after_supervisor(state: AgentState) -> str:
    """
    Conditional edge function called after the supervisor node.
    Returns the name of the next node to execute.
    """
    next_node = state.get("next_node", "NONE")

    if next_node == "NONE":
        return NODE_NO_AGENT
    if next_node == "UNCLEAR":
        return NODE_UNCLEAR

    # next_node is an agent_id → route to that agent's node
    agent_node_name = _agent_node_name(next_node)
    logger.info("Routing to agent node", node=agent_node_name)
    return agent_node_name


def _agent_node_name(agent_id: str) -> str:
    """Deterministic node name for an agent (sanitized for LangGraph)."""
    return f"agent__{agent_id.replace('-', '_')}"


# ─────────────────────────────────────────────────────────────────────────────
# Graph builder
# ─────────────────────────────────────────────────────────────────────────────

class OrchestratorGraph:
    """
    Builds and compiles the LangGraph StateGraph.

    The graph is compiled once at application startup with all currently
    active agents. For production hot-reload of agents, use a graph
    recompilation strategy or a single SpecializedAgentNode that accepts
    agent_id at runtime (see AgentGraphService).
    """

    def __init__(
        self,
        agents: list[Agent],
        supervisor_node: SupervisorNode,
        embedding_client: IEmbeddingClient,
        pinecone_client: PineconeClient,
        bedrock_client: BedrockClient,
    ) -> None:
        self._agents = agents
        self._supervisor = supervisor_node
        self._embedding = embedding_client
        self._pinecone = pinecone_client
        self._bedrock = bedrock_client
        self._compiled = self._build()

    def _build(self):  # type: ignore[no-untyped-def]
        """Build and compile the StateGraph."""
        builder = StateGraph(AgentState)

        # ── Add supervisor node ───────────────────────────────────────────────
        builder.add_node(NODE_SUPERVISOR, self._supervisor)

        # ── Add terminal nodes ────────────────────────────────────────────────
        builder.add_node(NODE_NO_AGENT, no_agent_node)
        builder.add_node(NODE_UNCLEAR, unclear_node)

        # ── Add dynamic specialized agent nodes ───────────────────────────────
        for agent in self._agents:
            node_name = _agent_node_name(agent.id)
            node = SpecializedAgentNode(
                agent=agent,
                embedding_client=self._embedding,
                pinecone_client=self._pinecone,
                bedrock_client=self._bedrock,
            )
            builder.add_node(node_name, node)
            # Each agent node goes directly to END after generating the answer
            builder.add_edge(node_name, END)
            logger.debug("Added agent node to graph", node=node_name, agent=agent.name)

        # Terminal nodes also end the graph
        builder.add_edge(NODE_NO_AGENT, END)
        builder.add_edge(NODE_UNCLEAR, END)

        # ── Entry point ───────────────────────────────────────────────────────
        builder.add_edge(START, NODE_SUPERVISOR)

        # ── Conditional routing after supervisor ──────────────────────────────
        possible_routes = (
            [NODE_NO_AGENT, NODE_UNCLEAR]
            + [_agent_node_name(a.id) for a in self._agents]
        )
        builder.add_conditional_edges(
            NODE_SUPERVISOR,
            route_after_supervisor,
            {route: route for route in possible_routes},
        )

        compiled = builder.compile()
        logger.info(
            "OrchestratorGraph compiled",
            agent_nodes=len(self._agents),
            total_nodes=len(self._agents) + 3,
        )
        return compiled

    async def invoke(
        self,
        user_query: str,
        user_id: str,
        session_id: str | None = None,
        agent_id: str | None = None,
        tenant_id: int = 1,
    ) -> AgentState:
        """
        Run the graph for a single user query.

        Returns the final AgentState after all nodes complete.
        """
        initial_state: AgentState = {
            "messages": [HumanMessage(content=user_query)],
            "user_id": user_id,
            "session_id": session_id,
            "tenant_id": tenant_id,
            "user_query": user_query,
            "agent_id": agent_id,
            "selected_agent": None,
            "routing_reason": None,
            "context_chunks": [],
            "sources": [],
            "final_answer": None,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "error": None,
            "next_node": "",
        }

        logger.info(
            "Graph invoked",
            user_id=user_id,
            agent_id=agent_id,
            query_preview=user_query[:80],
        )

        result = await self._compiled.ainvoke(initial_state)
        return result  # type: ignore[return-value]
