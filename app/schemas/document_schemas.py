"""
Pydantic schemas (DTOs) for the Documents API.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ── Response schemas ──────────────────────────────────────────────────────────

class DocumentResponse(BaseModel):
    id: str
    agent_id: str
    user_id: Optional[str]
    file_name: str
    mime_type: str
    file_size_bytes: int
    storage_path: str
    status: str
    error_message: Optional[str]
    total_chunks: int
    embedding_model: str
    chunk_size: int
    chunk_overlap: int
    uploaded_at: datetime
    processed_at: Optional[datetime]


class DocumentListResponse(BaseModel):
    total: int
    documents: list[DocumentResponse]


class DocumentUploadResponse(BaseModel):
    document: DocumentResponse
    processing_started: bool
    message: str = "Document uploaded. Processing started in the background."


class DocumentChunkResponse(BaseModel):
    id: str
    chunk_index: int
    vector_id: str
    text_preview: str
    page_from: Optional[int]
    page_to: Optional[int]
    token_count: int
    created_at: datetime


class DeleteResponse(BaseModel):
    success: bool
    message: str
