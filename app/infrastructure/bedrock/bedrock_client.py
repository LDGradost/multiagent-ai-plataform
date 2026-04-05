"""
Amazon Bedrock client for LLM inference.

Used ONLY for text generation (chat + routing).
NOT used for embeddings (Google Vertex AI handles that).

Supports Claude models via the converse API (the modern unified Bedrock API).
The converse API works with all Bedrock models that support conversational input.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional

import boto3
from botocore.exceptions import ClientError, BotoCoreError
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings
from app.core.exceptions import BedrockInferenceError
from app.core.logging import get_logger

logger = get_logger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Data types
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class BedrockMessage:
    """A single message in a Bedrock conversation."""
    role: str       # "user" | "assistant"
    content: str


@dataclass
class BedrockResponse:
    """Structured response from Bedrock inference."""
    content: str
    model_id: str
    stop_reason: str
    input_tokens: int
    output_tokens: int


# ─────────────────────────────────────────────────────────────────────────────
# Client
# ─────────────────────────────────────────────────────────────────────────────

class BedrockClient:
    """
    Thin adapter over boto3 bedrock-runtime for invoke via the Converse API.

    The Converse API (bedrock_runtime.converse) is model-agnostic and supports
    Claude 3/3.5, Llama 3, Mistral, and other Bedrock models uniformly.

    Usage:
        client = BedrockClient()
        response = await client.invoke(
            system_prompt="You are a helpful assistant.",
            messages=[BedrockMessage(role="user", content="Hello!")],
        )
    """

    def __init__(
        self,
        model_id: Optional[str] = None,
        region: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        aws_access_key_id: Optional[str] = None,
        aws_secret_access_key: Optional[str] = None,
    ) -> None:
        self._model_id = model_id or settings.bedrock_default_model_id
        self._max_tokens = max_tokens or settings.bedrock_max_tokens
        self._temperature = temperature if temperature is not None else settings.bedrock_temperature
        self._region = region or settings.aws_region

        session = boto3.Session(
            aws_access_key_id=aws_access_key_id or settings.aws_access_key_id or None,
            aws_secret_access_key=aws_secret_access_key or settings.aws_secret_access_key or None,
            region_name=self._region,
        )
        self._client = session.client("bedrock-runtime")

        logger.info(
            "BedrockClient initialized",
            model_id=self._model_id,
            region=self._region,
            max_tokens=self._max_tokens,
        )

    # ── Main invoke method (Converse API) ─────────────────────────────────────

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=20),
        reraise=True,
    )
    async def invoke(
        self,
        messages: list[BedrockMessage],
        system_prompt: Optional[str] = None,
        model_id: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> BedrockResponse:
        """
        Invoke a Bedrock model via the Converse API.

        Args:
            messages: Conversation history (user/assistant alternating).
            system_prompt: Optional system instructions prepended to the conversation.
            model_id: Override default model for this call.
            max_tokens: Override max tokens.
            temperature: Override temperature.

        Returns:
            BedrockResponse with content, usage stats and stop reason.
        """
        effective_model = model_id or self._model_id
        effective_max_tokens = max_tokens or self._max_tokens
        effective_temperature = temperature if temperature is not None else self._temperature

        converse_messages = [
            {"role": msg.role, "content": [{"text": msg.content}]}
            for msg in messages
        ]

        kwargs: dict = {
            "modelId": effective_model,
            "messages": converse_messages,
            "inferenceConfig": {
                "maxTokens": effective_max_tokens,
                "temperature": effective_temperature,
            },
        }

        if system_prompt:
            kwargs["system"] = [{"text": system_prompt}]

        try:
            logger.debug(
                "Bedrock invoke",
                model_id=effective_model,
                message_count=len(messages),
            )
            response = self._client.converse(**kwargs)
            output = response["output"]["message"]["content"][0]["text"]
            usage = response.get("usage", {})
            stop_reason = response.get("stopReason", "end_turn")

            logger.info(
                "Bedrock invoke complete",
                model_id=effective_model,
                input_tokens=usage.get("inputTokens", 0),
                output_tokens=usage.get("outputTokens", 0),
                stop_reason=stop_reason,
            )

            return BedrockResponse(
                content=output,
                model_id=effective_model,
                stop_reason=stop_reason,
                input_tokens=usage.get("inputTokens", 0),
                output_tokens=usage.get("outputTokens", 0),
            )

        except ClientError as exc:
            error_code = exc.response["Error"]["Code"]
            error_msg = exc.response["Error"]["Message"]
            logger.error(
                "Bedrock ClientError",
                model_id=effective_model,
                code=error_code,
                message=error_msg,
            )
            raise BedrockInferenceError(
                model_id=effective_model,
                detail=f"{error_code}: {error_msg}",
            ) from exc

        except BotoCoreError as exc:
            logger.error("Bedrock BotoCoreError", model_id=effective_model, error=str(exc))
            raise BedrockInferenceError(
                model_id=effective_model, detail=str(exc)
            ) from exc

    # ── Convenience: generate a single user turn ──────────────────────────────

    async def generate(
        self,
        user_message: str,
        system_prompt: Optional[str] = None,
        model_id: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> BedrockResponse:
        """
        Shortcut for single-turn generation.
        Wraps the user message as a one-turn conversation.
        """
        return await self.invoke(
            messages=[BedrockMessage(role="user", content=user_message)],
            system_prompt=system_prompt,
            model_id=model_id,
            max_tokens=max_tokens,
            temperature=temperature,
        )

    # ── Orchestrator routing (using lightweight model) ─────────────────────────

    async def route(
        self,
        user_message: str,
        system_prompt: str,
    ) -> str:
        """
        Lightweight routing call using the orchestrator model (e.g. Haiku).
        Returns raw text content — caller parses the routing decision.
        """
        response = await self.generate(
            user_message=user_message,
            system_prompt=system_prompt,
            model_id=settings.bedrock_orchestrator_model_id,
            max_tokens=512,
            temperature=0.0,  # deterministic routing
        )
        return response.content
