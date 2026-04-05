"""
Documents endpoints.

POST   /agents/{agent_id}/documents     → upload document to agent
GET    /agents/{agent_id}/documents     → list documents of agent
GET    /agents/{agent_id}/documents/{document_id} → get document detail
DELETE /documents/{document_id}         → delete document + vectors + file
"""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, File, Query, UploadFile, status

from app.application.services.upload_document_service import (
    UploadDocumentInput,
    UploadDocumentService,
)
from app.application.services.delete_document_service import DeleteDocumentService
from app.core.dependencies import (
    AgentRepoDep,
    ChunkRepoDep,
    DocumentRepoDep,
    KBRepoDep,
    PineconeClientDep,
    S3ClientDep,
    EmbeddingClientDep,
    ParserRegistryDep,
)
from app.core.exceptions import AgentNotFoundError, DocumentNotFoundError
from app.domain.entities.entities import Document
from app.schemas.document_schemas import (
    DeleteResponse,
    DocumentListResponse,
    DocumentResponse,
    DocumentUploadResponse,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Helper: domain → schema
# ---------------------------------------------------------------------------

def _doc_to_schema(doc: Document) -> DocumentResponse:
    return DocumentResponse(
        id=doc.id,
        agent_id=doc.agent_id,
        user_id=doc.user_id,
        file_name=doc.file_name,
        mime_type=doc.mime_type,
        file_size_bytes=doc.file_size_bytes,
        storage_path=doc.storage_path,
        status=doc.status.value,
        error_message=doc.error_message,
        total_chunks=doc.total_chunks,
        embedding_model=doc.embedding_model,
        chunk_size=doc.chunk_size,
        chunk_overlap=doc.chunk_overlap,
        uploaded_at=doc.uploaded_at,
        processed_at=doc.processed_at,
    )


# ---------------------------------------------------------------------------
# POST /agents/{agent_id}/documents
# ---------------------------------------------------------------------------

@router.post(
    "/{agent_id}/documents",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload a document to an agent's knowledge base",
    description=(
        "Uploads a file (PDF, DOCX, TXT, MD) to S3, registers it in the database, "
        "and starts async background processing: extract text → chunk → embed → upsert to Pinecone."
    ),
    tags=["Documents"],
)
async def upload_document(
    agent_id: str,
    background_tasks: BackgroundTasks,
    agent_repo: AgentRepoDep,
    kb_repo: KBRepoDep,
    document_repo: DocumentRepoDep,
    chunk_repo: ChunkRepoDep,
    s3_client: S3ClientDep,
    embedding_client: EmbeddingClientDep,
    pinecone_client: PineconeClientDep,
    parser_registry: ParserRegistryDep,
    file: UploadFile = File(..., description="Document file (PDF, DOCX, TXT, MD)"),
    user_id: str = Query(default="demo-user-id"),
) -> DocumentUploadResponse:
    content = await file.read()
    svc = UploadDocumentService(
        agent_repo=agent_repo,
        kb_repo=kb_repo,
        document_repo=document_repo,
        chunk_repo=chunk_repo,
        s3_client=s3_client,
        embedding_client=embedding_client,
        pinecone_client=pinecone_client,
        parser_registry=parser_registry,
    )
    result = await svc.execute(
        data=UploadDocumentInput(
            agent_id=agent_id,
            user_id=user_id,
            filename=file.filename or "document",
            content=content,
            content_type=file.content_type or "application/octet-stream",
        ),
        background_tasks=background_tasks,
    )
    return DocumentUploadResponse(
        document=_doc_to_schema(result.document),
        processing_started=result.processing_started,
    )


# ---------------------------------------------------------------------------
# GET /agents/{agent_id}/documents
# ---------------------------------------------------------------------------

@router.get(
    "/{agent_id}/documents",
    response_model=DocumentListResponse,
    summary="List all documents for an agent",
    tags=["Documents"],
)
async def list_documents(
    agent_id: str,
    agent_repo: AgentRepoDep,
    document_repo: DocumentRepoDep,
) -> DocumentListResponse:
    agent = await agent_repo.get_by_id(agent_id)
    if not agent:
        raise AgentNotFoundError(agent_id)

    docs = await document_repo.list_by_agent(agent_id)
    return DocumentListResponse(
        total=len(docs),
        documents=[_doc_to_schema(d) for d in docs],
    )


# ---------------------------------------------------------------------------
# GET /agents/{agent_id}/documents/{document_id}
# ---------------------------------------------------------------------------

@router.get(
    "/{agent_id}/documents/{document_id}",
    response_model=DocumentResponse,
    summary="Get a single document's details and processing status",
    tags=["Documents"],
)
async def get_document(
    agent_id: str,
    document_id: str,
    document_repo: DocumentRepoDep,
) -> DocumentResponse:
    doc = await document_repo.get_by_id(document_id)
    if not doc or doc.agent_id != agent_id:
        raise DocumentNotFoundError(document_id)
    return _doc_to_schema(doc)


# ---------------------------------------------------------------------------
# DELETE /documents/{document_id}
# (registered separately at /documents level in the main router)
# ---------------------------------------------------------------------------

@router.delete(
    "/documents/{document_id}",
    response_model=DeleteResponse,
    summary="Delete a document including its vectors (Pinecone) and original file (S3)",
    tags=["Documents"],
)
async def delete_document(
    document_id: str,
    document_repo: DocumentRepoDep,
    chunk_repo: ChunkRepoDep,
    kb_repo: KBRepoDep,
    pinecone_client: PineconeClientDep,
    s3_client: S3ClientDep,
) -> DeleteResponse:
    svc = DeleteDocumentService(
        document_repo=document_repo,
        chunk_repo=chunk_repo,
        kb_repo=kb_repo,
        pinecone_client=pinecone_client,
        s3_client=s3_client,
    )
    await svc.execute(document_id)
    return DeleteResponse(success=True, message=f"Document {document_id} deleted successfully.")
