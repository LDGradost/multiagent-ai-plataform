# Multi-Agent AI Platform

A production-ready **multi-agent AI platform** that dynamically routes user queries to specialized agents using **LLM-based orchestration** and **Retrieval-Augmented Generation (RAG)**.

Built with **FastAPI**, **LangGraph**, **Amazon Bedrock**, **Google Gemini Embeddings**, and **Pinecone**.

---

## Overview

Traditional AI systems struggle to handle multiple domains efficiently.

This platform solves that by:
- Splitting knowledge into **specialized agents**
- Using an **LLM supervisor** to route queries intelligently
- Grounding responses with **retrieved context (RAG)**
- Maintaining **isolated knowledge per agent**

---

##  System Overview

``` id="overview"
          ┌────────────────────┐
          │      USER          │
          └────────┬───────────┘
                   │ Query
                   ▼
        ┌──────────────────────┐
        │  SUPERVISOR (LLM)    │
        │  Routing Decision    │
        └────────┬─────────────┘
                 │ Select agent
                 ▼
        ┌──────────────────────┐
        │  SPECIALIZED AGENT   │
        └────────┬─────────────┘
                 │ Retrieve context
                 ▼
        ┌──────────────────────┐
        │     PINECONE         │
        │  Vector DB (RAG)     │
        └────────┬─────────────┘
                 │ Context
                 ▼
        ┌──────────────────────┐
        │   BEDROCK (LLM)      │
        │ Response generation  │
        └────────┬─────────────┘
                 ▼
          🧾 Answer + Sources

## Architecture Layers
┌─────────────────────────────┐
│ API Layer (FastAPI)         │
├─────────────────────────────┤
│ Application (Use Cases)     │
├─────────────────────────────┤
│ Agents (LangGraph)          │
│  - Supervisor               │
│  - Specialized Agents       │
├─────────────────────────────┤
│ Domain (Entities)           │
├─────────────────────────────┤
│ Infrastructure              │
│  - Pinecone                 │
│  - Bedrock                  │
│  - S3                       │
│  - PostgreSQL               │
└─────────────────────────────┘
## ✨ Features

- 🧠 **Multi-agent architecture** with dynamic LLM-based routing  
- 🔍 **Retrieval-Augmented Generation (RAG)** per agent  
- 📂 **Document ingestion pipeline** (parse → chunk → embed → index)  
- 🧩 **Namespace isolation per agent** in Pinecone  
- 📊 **Context-aware responses with source attribution**  
- ⚡ **Async background processing** for document ingestion  
- 💬 **Chat sessions with persistent history**  
- 🏗️ **Clean architecture (domain-driven design)**  
- 🔄 **Pluggable infrastructure (LLM, embeddings, vector DB)**  

---

## 🧪 Use Cases

- Domain-specific AI assistants (legal, finance, tech, etc.)
- Enterprise knowledge search systems
- AI copilots with structured knowledge bases
- Multi-domain conversational systems

---

## 🔄 How It Works

1. User sends a query  
2. The **Supervisor Agent (LLM)** selects the most relevant specialized agent  
3. The selected agent retrieves context from **Pinecone**  
4. The LLM generates a response using **retrieved knowledge only (RAG)**  
5. The system returns:
   - Answer  
   - Sources  
   - Token usage  

## 🧱 Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11 + FastAPI |
| Database | PostgreSQL (asyncpg + SQLAlchemy 2) |
| Migrations | Alembic |
| Storage | Amazon S3 |
| Embeddings | Google Gemini `gemini-embedding-2-preview` (3072d) |
| Vector DB | Pinecone (shared index + namespaces per agent) |
| LLM / Chat | Amazon Bedrock (`claude-3-5-sonnet`) |
| Orchestration | LangGraph + LangChain |
| Logging | structlog |

## 📁 Project Structure

app/
├── api/ # FastAPI routers and exception handlers
│ └── v1/
│ └── endpoints/ # agents.py, documents.py, chat.py, health.py
├── core/ # Config, logging, exceptions
├── domain/ # Business entities and interfaces
├── application/ # Use case services
├── agents/ # LangGraph orchestrator + specialized agents
├── infrastructure/ # DB, Pinecone, Bedrock, Embeddings, S3, Parsers
├── schemas/ # Pydantic DTOs
└── main.py # FastAPI entry point

## Data Flow (RAG Pipeline)

Upload Document
      ↓
Parse (PDF / DOCX / TXT)
      ↓
Chunking
      ↓
Embeddings (Gemini)
      ↓
Pinecone (Vector Storage)
      ↓
Query → Retrieve → Generate

## 🚀 Quick Start

```bash
# 1. Clone repository
git clone https://github.com/LDGradost/multiagent-ai-plataform.git
cd multiagent-ai-plataform

# 2. Create virtual environment
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux/Mac

# 3. Install dependencies
pip install -e ".[dev]"

# 4. Configure environment
cp .env.example .env
# Edit .env with your credentials

# 5. Run migrations
alembic upgrade head

# 6. Start the server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000


## Environment Variables

See .env.example for required configuration, including:

AWS (Bedrock + S3)
Google Cloud (Embeddings)
Pinecone
PostgreSQL

## Key Concepts
Multi-Agent Routing
An LLM-based supervisor selects the most relevant agent for each query.

RAG per Agent
Each agent operates over its own isolated knowledge base using Pinecone namespaces.

Clean Architecture
Strict separation of:
    Domain (business logic)
    Application (use cases)
    Infrastructure (external services)
Scalable Design
Stateless orchestration (LangGraph)
Async processing
Pluggable components


🧠 Why This Project Matters

This project demonstrates advanced capabilities in:

LLM orchestration (LangGraph)
Multi-agent system design
Retrieval-Augmented Generation (RAG)
AI system architecture for production
Backend engineering with scalable patterns


📌 Future Improvements
Streaming responses (real-time tokens)
Agent memory / long-term context
Evaluation framework (LLM metrics)
UI frontend (chat interface)
Observability (tracing, monitoring)


👤 Author

Developed by Luis Grados
AI Engineer | Multi-Agent Systems | RAG Architectures