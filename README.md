# Multi-Agent AI Platform

A production-ready multi-agent RAG platform built with **FastAPI**, **LangGraph**, **Amazon Bedrock**, **Google Gemini Embeddings** and **Pinecone**.

## Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11 + FastAPI |
| Database | PostgreSQL (asyncpg + SQLAlchemy 2) |
| Migrations | Alembic |
| Storage | Amazon S3 |
| Embeddings | Google Gemini `gemini-embedding-2-preview` (3072d) |
| Vector DB | Pinecone (1 shared index, namespaces per agent) |
| LLM / Chat | Amazon Bedrock (`claude-3-5-sonnet`) |
| Orchestration | LangGraph + LangChain |
| Logging | structlog |

## Quick Start

```bash
# 1. Clone and enter project
cd "Proyecto final"

# 2. Create virtual environment
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux/Mac

# 3. Install dependencies
pip install -e ".[dev]"

# 4. Configure environment
cp .env.example .env
# Edit .env with your credentials

# 5. Run migrations (after FASE 3)
alembic upgrade head

# 6. Start the server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Project Structure

```
app/
├── api/                    # FastAPI routers and exception handlers
│   └── v1/
│       └── endpoints/      # agents.py, documents.py, chat.py, health.py
├── core/                   # Config, logging, exceptions
├── domain/                 # Business entities and repository interfaces
├── application/            # Use case services
├── agents/                 # LangGraph orchestrator + specialized agents
├── infrastructure/         # DB, Pinecone, Bedrock, Embeddings, S3, Parsers
├── schemas/                # Pydantic DTOs
└── main.py                 # FastAPI entry point
tests/
├── unit/
├── integration/
└── fixtures/
```

## API Docs

Available at `http://localhost:8000/docs` (non-production only).

## Environment Variables

See `.env.example` for the full list of required variables.

## Phases

This project is built in 10 phases. See `FASE_*.md` architecture documents for details.
