"""
Global FastAPI exception handlers.
Maps domain/application exceptions to structured HTTP responses.
"""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.exceptions import (
    AgentNotFoundError,
    AgentAccessDeniedError,
    DocumentNotFoundError,
    KnowledgeBaseNotFoundError,
    ChatSessionNotFoundError,
    StorageUploadError,
    EmbeddingError,
    VectorUpsertError,
    VectorQueryError,
    BedrockInferenceError,
    DocumentParseError,
    InvalidFileTypeError,
    FileTooLargeError,
    OrchestratorRoutingError,
    NoAgentFoundError,
    AppBaseException,
)
from app.core.logging import get_logger

logger = get_logger(__name__)


def _error_response(code: str, message: str, status_code: int) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}},
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register all exception handlers on the FastAPI app."""

    @app.exception_handler(AgentNotFoundError)
    async def agent_not_found(_: Request, exc: AgentNotFoundError) -> JSONResponse:
        return _error_response(exc.code, exc.message, 404)

    @app.exception_handler(AgentAccessDeniedError)
    async def agent_access_denied(_: Request, exc: AgentAccessDeniedError) -> JSONResponse:
        return _error_response(exc.code, exc.message, 403)

    @app.exception_handler(DocumentNotFoundError)
    async def doc_not_found(_: Request, exc: DocumentNotFoundError) -> JSONResponse:
        return _error_response(exc.code, exc.message, 404)

    @app.exception_handler(KnowledgeBaseNotFoundError)
    async def kb_not_found(_: Request, exc: KnowledgeBaseNotFoundError) -> JSONResponse:
        return _error_response(exc.code, exc.message, 404)

    @app.exception_handler(ChatSessionNotFoundError)
    async def session_not_found(_: Request, exc: ChatSessionNotFoundError) -> JSONResponse:
        return _error_response(exc.code, exc.message, 404)

    @app.exception_handler(InvalidFileTypeError)
    async def invalid_file(_: Request, exc: InvalidFileTypeError) -> JSONResponse:
        return _error_response(exc.code, exc.message, 422)

    @app.exception_handler(FileTooLargeError)
    async def file_too_large(_: Request, exc: FileTooLargeError) -> JSONResponse:
        return _error_response(exc.code, exc.message, 413)

    @app.exception_handler(NoAgentFoundError)
    async def no_agent(_: Request, exc: NoAgentFoundError) -> JSONResponse:
        return _error_response(exc.code, exc.message, 422)

    @app.exception_handler(OrchestratorRoutingError)
    async def routing_error(_: Request, exc: OrchestratorRoutingError) -> JSONResponse:
        return _error_response(exc.code, exc.message, 422)

    @app.exception_handler(AppBaseException)
    async def app_base(_: Request, exc: AppBaseException) -> JSONResponse:
        logger.error("Unhandled app exception", code=exc.code, message=exc.message)
        return _error_response(exc.code, exc.message, 500)

    @app.exception_handler(Exception)
    async def unhandled(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled exception", exc_info=exc)
        return _error_response(
            "INTERNAL_ERROR",
            "An unexpected error occurred. Please try again later.",
            500,
        )
