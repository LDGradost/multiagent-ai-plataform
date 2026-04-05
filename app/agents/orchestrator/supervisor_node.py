"""
Supervisor node — analyzes the user query and selects the correct agent.

LangChain role: formats the routing prompt with available agents.
LangGraph role: sets state.next_node to route the graph to the right subagent.

Uses BedrockClient.route() with the lightweight model for cost efficiency.
"""
from __future__ import annotations

import json
from typing import Any

from app.agents.graph.state import AgentState
from app.agents.graph.prompts import SUPERVISOR_SYSTEM_PROMPT
from app.core.logging import get_logger
from app.infrastructure.bedrock.bedrock_client import BedrockClient
from app.infrastructure.db.repositories.agent_repository import AgentRepository

logger = get_logger(__name__)


class SupervisorNode:
    """
    LangGraph node: routes the user query to the most relevant agent.

    Decision outcomes (stored in state.next_node):
    - agent_id  → route to that specialized agent node
    - "NONE"    → no matching agent found
    - "UNCLEAR" → query is ambiguous, ask for clarification
    - "ERROR"   → unexpected failure
    """

    # Node name used in the graph
    NAME = "supervisor"

    def __init__(
        self,
        agent_repo: AgentRepository,
        bedrock_client: BedrockClient,
    ) -> None:
        self._agent_repo = agent_repo
        self._bedrock = bedrock_client

    async def __call__(self, state: AgentState) -> dict[str, Any]:
        """
        Entry point called by LangGraph.
        Returns a partial state update dict.
        """
        query = state["user_query"]
        logger.info("SupervisorNode invoked", query_preview=query[:80])

        # If agent_id was already set by the caller, skip routing
        if state.get("agent_id"):
            agent = await self._agent_repo.get_by_id(state["agent_id"])
            if agent and agent.is_active:
                return {
                    "selected_agent": agent,
                    "routing_reason": "Direct routing — agent_id provided by client",
                    "next_node": agent.id,
                }

        # Load all active agents for the routing prompt
        active_agents = await self._agent_repo.list_all_active()
        if not active_agents:
            return {
                "next_node": "NONE",
                "routing_reason": "No active agents exist in the system",
                "error": "NO_AGENTS",
            }

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

        system_prompt = SUPERVISOR_SYSTEM_PROMPT.format(agents_json=agents_json)

        # Call Bedrock with the lightweight routing model
        raw = await self._bedrock.route(
            user_message=query,
            system_prompt=system_prompt,
        )

        # Parse the JSON routing decision
        chosen_id, reason = self._parse_routing_response(raw)

        logger.info(
            "Supervisor routing decision",
            chosen_id=chosen_id,
            reason=reason,
        )

        if chosen_id in ("NONE", "UNCLEAR"):
            return {
                "next_node": chosen_id,
                "routing_reason": reason,
                "selected_agent": None,
            }

        # Find the chosen agent entity
        selected = next((a for a in active_agents if a.id == chosen_id), None)
        if not selected:
            logger.warning("Supervisor chose unknown agent_id", chosen_id=chosen_id)
            return {
                "next_node": "NONE",
                "routing_reason": f"Routing returned unknown agent_id: {chosen_id}",
            }

        return {
            "selected_agent": selected,
            "routing_reason": reason,
            "next_node": selected.id,
        }

    @staticmethod
    def _parse_routing_response(raw: str) -> tuple[str, str]:
        """Parse the routing JSON response from Bedrock."""
        try:
            # Strip markdown code fences if model added them
            clean = raw.strip().strip("```json").strip("```").strip()
            data = json.loads(clean)
            return data.get("agent_id", "NONE"), data.get("reason", "")
        except (json.JSONDecodeError, AttributeError):
            logger.warning("Failed to parse routing response", raw=raw[:300])
            return "NONE", "Could not parse routing response"
