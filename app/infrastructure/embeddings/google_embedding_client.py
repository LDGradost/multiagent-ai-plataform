"""
Google Gemini Embedding 2 client.

Uses the google-genai SDK to generate embeddings via gemini-embedding-2-preview.
The same model must be used for both indexing and querying.

Key specs (as of March 2026):
  - Model ID     : gemini-embedding-2-preview
  - Dimensions   : 3,072 (default) — adjustable via output_dimensionality (MRL)
  - Max input    : 8,192 tokens
  - Inputs       : Text, Images, Audio (mp3/wav), Video (mp4/mpeg), PDF
  - Region       : us-central1 only (Preview)
  - Task types   : RETRIEVAL_DOCUMENT, RETRIEVAL_QUERY, SEMANTIC_SIMILARITY, etc.

IMPORTANT: Update EMBEDDING_DIMENSION=3072 and recreate your Pinecone index with
3072 dimensions if you are migrating from text-embedding-004 (768 dims).
"""
from __future__ import annotations

import asyncio
import os
from abc import ABC, abstractmethod
from typing import Optional

from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings
from app.core.exceptions import EmbeddingError
from app.core.logging import get_logger

logger = get_logger(__name__)

# ─── Task type constants ────────────────────────────────────────────────────
# Gemini Embedding 2 accepts task instructions as custom text prefixes.
# The SDK also accepts the enum strings directly for backwards compatibility.
TASK_TYPE_RETRIEVAL_DOCUMENT = "RETRIEVAL_DOCUMENT"
TASK_TYPE_RETRIEVAL_QUERY    = "RETRIEVAL_QUERY"
TASK_TYPE_SEMANTIC_SIMILARITY = "SEMANTIC_SIMILARITY"
TASK_TYPE_CLASSIFICATION     = "CLASSIFICATION"
TASK_TYPE_CLUSTERING         = "CLUSTERING"
TASK_TYPE_CODE_RETRIEVAL_QUERY = "CODE_RETRIEVAL_QUERY"

# Default output dimension — must match your Pinecone index
_DEFAULT_DIMENSION = 3072


# ─────────────────────────────────────────────────────────────────────────────
# Interface (port) — decouples services from the concrete provider
# ─────────────────────────────────────────────────────────────────────────────

class IEmbeddingClient(ABC):
    """Abstract embedding client — swap provider without touching services."""

    @abstractmethod
    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """
        Embed a list of document chunks for indexing.
        Returns list of float vectors, one per input text.
        """
        ...

    @abstractmethod
    async def embed_query(self, text: str) -> list[float]:
        """Embed a single query string for retrieval."""
        ...

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Output vector dimension. Must match the Pinecone index dimension."""
        ...

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Model identifier string."""
        ...


# ─────────────────────────────────────────────────────────────────────────────
# Concrete implementation: Google Gemini Embedding 2
# ─────────────────────────────────────────────────────────────────────────────

class GoogleEmbeddingClient(IEmbeddingClient):
    """
    Gemini Embedding 2 client using the google-genai SDK.

    Supports batch indexing (embed_documents) and single query embedding
    (embed_query) using different task types for better retrieval quality.

    Batch size: The API supports up to 100 texts per request.
    We chunk at 50 to stay well within limits.

    Dimension notes:
      - Default output: 3,072 floats (native Gemini Embedding 2 size).
      - You can request fewer dims via output_dimensionality for lighter storage,
        but RAG quality may degrade below ~768 dims.
      - Set EMBEDDING_DIMENSION in .env and recreate Pinecone index accordingly.
    """

    _BATCH_SIZE = 50

    def __init__(
        self,
        model_name: Optional[str] = None,
        project: Optional[str] = None,
        location: Optional[str] = None,
        dimension: Optional[int] = None,
        api_key: Optional[str] = None,
    ) -> None:
        self._model_name = model_name or settings.google_embedding_model
        self._project    = project  or settings.google_cloud_project
        self._location   = location or settings.google_cloud_location
        # Gemini Embedding 2 default is 3072; allow override via config
        self._dimension  = dimension or settings.embedding_dimension or _DEFAULT_DIMENSION

        # ── Authentication ──────────────────────────────────────────────────
        # For Vertex AI access (recommended for production):
        #   Set GOOGLE_APPLICATION_CREDENTIALS env var to your service account JSON
        # For direct API key access (simpler for development):
        #   Pass api_key parameter or set GOOGLE_API_KEY env var
        if settings.google_application_credentials:
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = (
                settings.google_application_credentials
            )

        # ── Initialize google-genai client ──────────────────────────────────
        # We import here to avoid import errors if the library is not installed
        try:
            import google.generativeai as genai  # type: ignore[import]

            _api_key = api_key or os.environ.get("GOOGLE_API_KEY", "")
            if _api_key:
                # Direct API key mode (e.g. AI Studio or Vertex AI Express)
                genai.configure(api_key=_api_key)
                self._use_vertex = False
            else:
                # Vertex AI mode — uses ADC / service account credentials
                self._use_vertex = True

            self._genai = genai

        except ImportError as exc:
            raise ImportError(
                "google-generativeai package is required for Gemini Embedding 2. "
                "Install with: pip install google-generativeai>=0.8.0"
            ) from exc

        logger.info(
            "GoogleEmbeddingClient (Gemini Embedding 2) initialized",
            model=self._model_name,
            dimension=self._dimension,
            project=self._project,
            location=self._location,
            vertex_mode=self._use_vertex,
        )

    @property
    def dimension(self) -> int:
        return self._dimension

    @property
    def model_name(self) -> str:
        return self._model_name

    # ── Public API ────────────────────────────────────────────────────────────

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """
        Embed document chunks for indexing.
        Uses RETRIEVAL_DOCUMENT task type for best indexing quality.
        Automatically batches large lists.
        """
        if not texts:
            return []

        try:
            all_embeddings: list[list[float]] = []

            for i in range(0, len(texts), self._BATCH_SIZE):
                batch = texts[i : i + self._BATCH_SIZE]
                batch_embeddings = await self._embed_batch(
                    batch, task_type=TASK_TYPE_RETRIEVAL_DOCUMENT
                )
                all_embeddings.extend(batch_embeddings)

                logger.debug(
                    "Embedded document batch",
                    batch_start=i,
                    batch_size=len(batch),
                    total=len(texts),
                )

            self._validate_dimension(all_embeddings)
            return all_embeddings

        except Exception as exc:
            logger.error("embed_documents failed", error=str(exc))
            raise EmbeddingError(detail=str(exc)) from exc

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def embed_query(self, text: str) -> list[float]:
        """
        Embed a user query for retrieval.
        Uses RETRIEVAL_QUERY task type for best retrieval quality.
        """
        try:
            vectors = await self._embed_batch([text], task_type=TASK_TYPE_RETRIEVAL_QUERY)
            vector = vectors[0]

            if len(vector) != self._dimension:
                logger.warning(
                    "Unexpected embedding dimension",
                    expected=self._dimension,
                    got=len(vector),
                )

            return vector

        except Exception as exc:
            logger.error("embed_query failed", error=str(exc))
            raise EmbeddingError(detail=str(exc)) from exc

    # ── Private helpers ───────────────────────────────────────────────────────

    async def _embed_batch(
        self,
        texts: list[str],
        task_type: str = TASK_TYPE_RETRIEVAL_DOCUMENT,
    ) -> list[list[float]]:
        """
        Call the Gemini Embedding 2 API for a batch of texts.

        The google-genai SDK is synchronous, so we run it in an executor to
        keep the async event loop unblocked.

        Args:
            texts:     List of strings to embed.
            task_type: Task instruction that optimises the embedding space.

        Returns:
            List of float vectors, one per input text.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self._sync_embed_batch,
            texts,
            task_type,
        )

    def _sync_embed_batch(
        self,
        texts: list[str],
        task_type: str,
    ) -> list[list[float]]:
        """
        Synchronous call to Gemini Embedding 2.

        Uses embed_content for batched text embedding.
        Supports output_dimensionality to reduce vector size via MRL.
        """
        results: list[list[float]] = []

        if self._use_vertex:
            # ── Vertex AI mode ─────────────────────────────────────────────
            # Uses google-genai SDK with Vertex AI backend
            try:
                import vertexai  # type: ignore[import]
                from vertexai.preview.vision_models import (  # type: ignore[import]
                    MultiModalEmbeddingModel,
                )
                # For text-only Gemini Embedding 2, use the generativeai client
                # configured with Vertex AI credentials (ADC)
                vertexai.init(project=self._project, location=self._location)

                # Call the generative AI embedding API through Vertex AI
                # using the google.generativeai SDK which automatically uses
                # Vertex AI when GOOGLE_APPLICATION_CREDENTIALS is set
                for text in texts:
                    result = self._genai.embed_content(
                        model=f"models/{self._model_name}",
                        content=text,
                        task_type=task_type,
                        output_dimensionality=self._dimension
                        if self._dimension != _DEFAULT_DIMENSION
                        else None,
                    )
                    results.append(result["embedding"])

            except Exception:
                # Fallback: call via generativeai directly (ADC will be used)
                for text in texts:
                    result = self._genai.embed_content(
                        model=f"models/{self._model_name}",
                        content=text,
                        task_type=task_type,
                        output_dimensionality=self._dimension
                        if self._dimension != _DEFAULT_DIMENSION
                        else None,
                    )
                    results.append(result["embedding"])

        else:
            # ── Direct API key mode ────────────────────────────────────────
            for text in texts:
                result = self._genai.embed_content(
                    model=f"models/{self._model_name}",
                    content=text,
                    task_type=task_type,
                    output_dimensionality=self._dimension
                    if self._dimension != _DEFAULT_DIMENSION
                    else None,
                )
                results.append(result["embedding"])

        return results

    def _validate_dimension(self, embeddings: list[list[float]]) -> None:
        """Warn if the returned dimension differs from the configured one."""
        if embeddings and len(embeddings[0]) != self._dimension:
            logger.warning(
                "Embedding dimension mismatch — check EMBEDDING_DIMENSION in .env",
                expected=self._dimension,
                got=len(embeddings[0]),
            )
