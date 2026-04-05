"""
Custom exceptions for the Multi-Agent AI Platform.
All domain and application errors extend from these base classes.
"""
from __future__ import annotations


class AppBaseException(Exception):
    """Base class for all application exceptions."""

    def __init__(self, message: str, code: str = "INTERNAL_ERROR") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


# ── Domain Exceptions ─────────────────────────────────────────────────────────

class AgentNotFoundError(AppBaseException):
    def __init__(self, agent_id: str) -> None:
        super().__init__(f"Agent '{agent_id}' not found.", code="AGENT_NOT_FOUND")


class AgentAccessDeniedError(AppBaseException):
    def __init__(self, agent_id: str) -> None:
        super().__init__(
            f"Access denied to agent '{agent_id}'.", code="AGENT_ACCESS_DENIED"
        )


class DocumentNotFoundError(AppBaseException):
    def __init__(self, document_id: str) -> None:
        super().__init__(
            f"Document '{document_id}' not found.", code="DOCUMENT_NOT_FOUND"
        )


class KnowledgeBaseNotFoundError(AppBaseException):
    def __init__(self, kb_id: str) -> None:
        super().__init__(
            f"KnowledgeBase '{kb_id}' not found.", code="KB_NOT_FOUND"
        )


class ChatSessionNotFoundError(AppBaseException):
    def __init__(self, session_id: str) -> None:
        super().__init__(
            f"Chat session '{session_id}' not found.", code="SESSION_NOT_FOUND"
        )


# ── Infrastructure Exceptions ─────────────────────────────────────────────────

class StorageUploadError(AppBaseException):
    def __init__(self, filename: str, detail: str = "") -> None:
        super().__init__(
            f"Failed to upload '{filename}' to storage. {detail}",
            code="STORAGE_UPLOAD_ERROR",
        )


class EmbeddingError(AppBaseException):
    def __init__(self, detail: str = "") -> None:
        super().__init__(
            f"Embedding generation failed. {detail}", code="EMBEDDING_ERROR"
        )


class VectorUpsertError(AppBaseException):
    def __init__(self, detail: str = "") -> None:
        super().__init__(
            f"Pinecone upsert failed. {detail}", code="VECTOR_UPSERT_ERROR"
        )


class VectorQueryError(AppBaseException):
    def __init__(self, detail: str = "") -> None:
        super().__init__(
            f"Pinecone query failed. {detail}", code="VECTOR_QUERY_ERROR"
        )


class BedrockInferenceError(AppBaseException):
    def __init__(self, model_id: str, detail: str = "") -> None:
        super().__init__(
            f"Bedrock inference failed for model '{model_id}'. {detail}",
            code="BEDROCK_INFERENCE_ERROR",
        )


class DocumentParseError(AppBaseException):
    def __init__(self, filename: str, detail: str = "") -> None:
        super().__init__(
            f"Failed to parse document '{filename}'. {detail}",
            code="DOCUMENT_PARSE_ERROR",
        )


# ── Application Exceptions ────────────────────────────────────────────────────

class InvalidFileTypeError(AppBaseException):
    def __init__(self, extension: str) -> None:
        super().__init__(
            f"File type '.{extension}' is not allowed.", code="INVALID_FILE_TYPE"
        )


class FileTooLargeError(AppBaseException):
    def __init__(self, max_mb: int) -> None:
        super().__init__(
            f"File exceeds maximum allowed size of {max_mb}MB.",
            code="FILE_TOO_LARGE",
        )


class OrchestratorRoutingError(AppBaseException):
    def __init__(self, detail: str = "") -> None:
        super().__init__(
            f"Orchestrator could not route the query. {detail}",
            code="ROUTING_ERROR",
        )


class NoAgentFoundError(AppBaseException):
    def __init__(self) -> None:
        super().__init__(
            "No suitable agent found for this query.", code="NO_AGENT_FOUND"
        )
