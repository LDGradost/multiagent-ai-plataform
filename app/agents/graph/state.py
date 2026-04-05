"""
Graph state definition for the LangGraph multi-agent orchestration.

The state object is passed between every node in the graph.
LangGraph automatically merges state updates from each node.
"""
from __future__ import annotations

from typing import Annotated, Any, Optional

from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage


class AgentState(dict):
    """
    Typed state that flows through every node in the LangGraph.

    Fields:
        messages:       Full conversation history (LangChain BaseMessage list).
                        `add_messages` reducer appends instead of replacing.
        user_id:        ID of the requesting user.
        session_id:     Active chat session ID (may be None on first turn).
        tenant_id:      Tenant scoping (for namespace resolution).
        user_query:     Raw text of the user's query.
        agent_id:       If set, skip routing and go directly to this agent.
        selected_agent: The Agent entity chosen by the supervisor or client.
        routing_reason: Human-readable routing decision explanation.
        context_chunks: Pinecone results — list of QueryResult objects.
        sources:        ChatSource list to include in the final response.
        final_answer:   The generated answer text.
        prompt_tokens:  Input tokens consumed by Bedrock.
        completion_tokens: Output tokens consumed by Bedrock.
        error:          Set if any node raises and is caught gracefully.
        next_node:      Control field set by the supervisor to route the graph.
    """

    messages: Annotated[list[BaseMessage], add_messages]
    user_id: str
    session_id: Optional[str]
    tenant_id: int
    user_query: str
    agent_id: Optional[str]           # direct routing if provided
    selected_agent: Optional[Any]     # domain Agent entity
    routing_reason: Optional[str]
    context_chunks: list[Any]         # list of QueryResult
    sources: list[Any]                # list of ChatSource
    final_answer: Optional[str]
    prompt_tokens: int
    completion_tokens: int
    error: Optional[str]
    next_node: str                    # "route" | "direct" | agent_id | END
