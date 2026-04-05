"""
Document parsers — extract raw text from uploaded files.
Supports: PDF, DOCX, TXT, Markdown, and optionally OCR for scanned PDFs.
"""
from __future__ import annotations

import io
from abc import ABC, abstractmethod

from app.core.config import settings
from app.core.exceptions import DocumentParseError
from app.core.logging import get_logger

logger = get_logger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Interface
# ─────────────────────────────────────────────────────────────────────────────

class IDocumentParser(ABC):
    @abstractmethod
    def extract_text(self, content: bytes, filename: str) -> str:
        """Extract plain text from raw file bytes."""
        ...

    @property
    @abstractmethod
    def supported_extensions(self) -> list[str]:
        """File extensions this parser handles."""
        ...


# ─────────────────────────────────────────────────────────────────────────────
# PDF Parser
# ─────────────────────────────────────────────────────────────────────────────

class PDFParser(IDocumentParser):
    """Extract text from PDF files using pypdf. Falls back to OCR if configured."""

    @property
    def supported_extensions(self) -> list[str]:
        return ["pdf"]

    def extract_text(self, content: bytes, filename: str) -> str:
        try:
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(content))
            pages: list[str] = []
            for page in reader.pages:
                text = page.extract_text() or ""
                pages.append(text)

            full_text = "\n\n".join(pages).strip()

            # If extraction yielded almost nothing, try OCR
            if len(full_text) < 50 and settings.ocr_enabled:
                logger.info("PDF text too short — attempting OCR", filename=filename)
                full_text = self._ocr_pdf(content, filename)

            logger.info(
                "PDF parsed",
                filename=filename,
                pages=len(pages),
                chars=len(full_text),
            )
            return full_text

        except Exception as exc:
            raise DocumentParseError(filename=filename, detail=str(exc)) from exc

    def _ocr_pdf(self, content: bytes, filename: str) -> str:
        """OCR fallback using pytesseract + Pillow (requires Tesseract on system)."""
        try:
            import pytesseract
            from PIL import Image
            from pypdf import PdfReader
            import fitz  # PyMuPDF — add to dependencies if OCR needed

            doc = fitz.open(stream=content, filetype="pdf")
            texts: list[str] = []
            for page in doc:
                pix = page.get_pixmap(dpi=300)
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                text = pytesseract.image_to_string(img, lang=settings.ocr_language)
                texts.append(text)
            return "\n\n".join(texts).strip()
        except Exception as exc:
            logger.warning("OCR failed", filename=filename, error=str(exc))
            return ""


# ─────────────────────────────────────────────────────────────────────────────
# DOCX Parser
# ─────────────────────────────────────────────────────────────────────────────

class DOCXParser(IDocumentParser):
    @property
    def supported_extensions(self) -> list[str]:
        return ["docx"]

    def extract_text(self, content: bytes, filename: str) -> str:
        try:
            from docx import Document

            doc = Document(io.BytesIO(content))
            paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
            full_text = "\n\n".join(paragraphs)
            logger.info("DOCX parsed", filename=filename, chars=len(full_text))
            return full_text
        except Exception as exc:
            raise DocumentParseError(filename=filename, detail=str(exc)) from exc


# ─────────────────────────────────────────────────────────────────────────────
# TXT Parser
# ─────────────────────────────────────────────────────────────────────────────

class TXTParser(IDocumentParser):
    @property
    def supported_extensions(self) -> list[str]:
        return ["txt"]

    def extract_text(self, content: bytes, filename: str) -> str:
        try:
            # Try UTF-8, fall back to latin-1
            for encoding in ("utf-8", "latin-1", "cp1252"):
                try:
                    return content.decode(encoding)
                except UnicodeDecodeError:
                    continue
            raise DocumentParseError(filename=filename, detail="Cannot decode text file")
        except DocumentParseError:
            raise
        except Exception as exc:
            raise DocumentParseError(filename=filename, detail=str(exc)) from exc


# ─────────────────────────────────────────────────────────────────────────────
# Markdown Parser
# ─────────────────────────────────────────────────────────────────────────────

class MarkdownParser(IDocumentParser):
    @property
    def supported_extensions(self) -> list[str]:
        return ["md", "markdown"]

    def extract_text(self, content: bytes, filename: str) -> str:
        try:
            import markdown
            from html.parser import HTMLParser

            class _MLStripper(HTMLParser):
                def __init__(self) -> None:
                    super().__init__()
                    self.fed: list[str] = []

                def handle_data(self, d: str) -> None:
                    self.fed.append(d)

                def get_data(self) -> str:
                    return " ".join(self.fed)

            raw = content.decode("utf-8", errors="replace")
            html = markdown.markdown(raw)
            stripper = _MLStripper()
            stripper.feed(html)
            return stripper.get_data()
        except Exception as exc:
            raise DocumentParseError(filename=filename, detail=str(exc)) from exc


# ─────────────────────────────────────────────────────────────────────────────
# Parser Registry — dispatches by file extension
# ─────────────────────────────────────────────────────────────────────────────

class DocumentParserRegistry:
    """
    Central registry of parsers.
    Uses file extension to select the correct parser.
    """

    def __init__(self) -> None:
        self._parsers: dict[str, IDocumentParser] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        for parser in [PDFParser(), DOCXParser(), TXTParser(), MarkdownParser()]:
            for ext in parser.supported_extensions:
                self._parsers[ext.lower()] = parser

    def register(self, parser: IDocumentParser) -> None:
        """Register a custom parser (extensible without modifying this file)."""
        for ext in parser.supported_extensions:
            self._parsers[ext.lower()] = parser

    def parse(self, content: bytes, filename: str) -> str:
        """Select the correct parser and extract text."""
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        parser = self._parsers.get(ext)
        if not parser:
            raise DocumentParseError(
                filename=filename,
                detail=f"No parser available for extension '.{ext}'",
            )
        return parser.extract_text(content, filename)

    def supports(self, filename: str) -> bool:
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        return ext in self._parsers
