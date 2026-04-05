# FASE 8 — Ejemplo End-to-End

Esta fase demuestra el flujo completo del sistema multi-agente desde cero.

## Pre-requisitos

```bash
# Backend corriendo
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Variables de entorno configuradas (.env)
# - DATABASE_URL apuntando a PostgreSQL
# - PINECONE_API_KEY
# - AWS credentials (Bedrock + S3)
# - GOOGLE_APPLICATION_CREDENTIALS (Embeddings)
```

---

## Flujo End-to-End

```
Usuario → [1] Crear Agente → [2] Subir Documento
                                      ↓
                              background pipeline:
                              parse → chunk → embed (Google) → upsert (Pinecone)
                                      ↓
                              [3] Consulta de Chat
                              Orchestrator (Bedrock Haiku) → selecciona agente
                              Specialized Agent:
                                embed query → Pinecone RAG → Bedrock → respuesta
                                      ↓
                              [4] ChatResponse con sources[]
```

---

## Opción A — Script Python automático

```bash
pip install httpx rich
python e2e_demo.py
```

El script:
- Crea un agente "HP LaserJet Expert" vía API
- Sube un manual técnico de HP (texto embebido en el script)
- Hace polling hasta que el documento esté `ready` (Pinecone upsert completado)
- Envía una consulta al orquestador (sin `agent_id`, routing automático)
- Imprime la respuesta formateada con fuentes, tokens y session ID

---

## Opción B — VS Code REST Client (demo.http)

1. Instala la extensión **REST Client** en VS Code
2. Abre `demo.http`
3. Ejecuta cada request en orden haciendo clic en **Send Request**
4. Actualiza las variables `@agent_id`, `@document_id`, `@session_id` con los valores devueltos

---

## Opción C — Swagger UI

Navega a: **[http://localhost:8000/docs](http://localhost:8000/docs)**

Orden de ejecución:

| # | Endpoint | Método | Descripción |
|---|----------|--------|-------------|
| 1 | `/api/v1/agents` | `POST` | Crear agente |
| 2 | `/api/v1/agents/{id}/documents` | `POST` | Subir documento |
| 3 | `/api/v1/agents/{id}/documents/{doc_id}` | `GET` | Verificar status (polling) |
| 4 | `/api/v1/chat` | `POST` | Consulta (sin `agent_id` = orquestador) |
| 5 | `/api/v1/chat/sessions/{session_id}` | `GET` | Ver historial con fuentes |

---

## Paso 1 — Crear Agente

**Request:**
```http
POST /api/v1/agents?user_id=demo-user-id&tenant_id=1
Content-Type: application/json

{
  "name": "HP LaserJet Expert",
  "topic": "Impresoras HP LaserJet",
  "description": "Soporte técnico oficial HP LaserJet Pro",
  "system_prompt": "Eres un experto técnico en impresoras HP LaserJet. Responde únicamente basándote en la documentación técnica oficial de HP. Si la respuesta no está en el contexto, indícalo.",
  "llm_model": "anthropic.claude-3-5-sonnet-20241022-v2:0",
  "llm_temperature": 0.1,
  "llm_max_tokens": 2048
}
```

**Respuesta (201 Created):**
```json
{
  "id": "a1b2c3d4-...",
  "name": "HP LaserJet Expert",
  "topic": "Impresoras HP LaserJet",
  "pinecone_namespace": "tenant_1_user_demo-user-id_agent_a1b2c3d4",
  "embedding_model": "text-embedding-004",
  "llm_model": "anthropic.claude-3-5-sonnet-20241022-v2:0",
  "is_active": true,
  "knowledge_base": {
    "status": "active",
    "total_documents": 0,
    "total_chunks": 0
  }
}
```

> ⚠️ Nota crítica: el namespace Pinecone se genera aquí pero **NO se crea ningún índice**. El namespace existe solo lógicamente en PostgreSQL hasta el primer `upsert`.

---

## Paso 2 — Subir Documento

**Request:**
```http
POST /api/v1/agents/{agent_id}/documents?user_id=demo-user-id
Content-Type: multipart/form-data

file: hp_laserjet_manual.pdf
```

**Respuesta (202 Accepted):**
```json
{
  "document": {
    "id": "d1e2f3g4-...",
    "file_name": "hp_laserjet_manual.pdf",
    "status": "uploaded",
    "total_chunks": 0
  },
  "processing_started": true
}
```

**Pipeline de procesamiento (background):**

```
status: uploaded
  → DocumentParser (PDF/TXT/DOCX/MD)
status: processing
  → RecursiveCharacterTextSplitter (chunk_size=1000, overlap=200)
  → GoogleEmbeddingClient.embed_documents()   ← gemini/text-embedding-004
  → PineconeClient.upsert(namespace=agent.namespace)
    metadata por vector:
      chunk_id, document_id, agent_id, filename, text,
      chunk_index, page_from, page_to, created_at
  → DocumentChunk records → PostgreSQL
status: ready  ✓  (o failed si error)
```

**Polling para verificar:**
```http
GET /api/v1/agents/{agent_id}/documents/{document_id}
```
Repetir hasta que `"status": "ready"`.

---

## Paso 3 — Consulta de Chat

### Modo A: Orquestador automático (recomendado)

```http
POST /api/v1/chat
Content-Type: application/json

{
  "user_id": "demo-user-id",
  "message": "¿Cuál es el cartucho de tóner de alta capacidad recomendado?",
  "tenant_id": 1
}
```

**Internamente (LangGraph):**
```
[supervisor_node]
  → Carga agentes activos de PostgreSQL
  → Llama Bedrock (Claude Haiku) con routing prompt:
     "Dado el mensaje del usuario y estos agentes disponibles,
      ¿cuál es el más adecuado? Responde con JSON: {agent_id: ...}"
  → Parsea agent_id seleccionado

[specialized_agent_node (HP LaserJet Expert)]
  → GoogleEmbeddingClient.embed_query(message)
  → PineconeClient.query(namespace="tenant_1_user_demo-user-id_agent_...", top_k=5)
  → Construye contexto RAG: system_prompt + chunks_text
  → BedrockClient.invoke(claude-3-5-sonnet, contexto + pregunta)
  → Retorna respuesta + sources
```

### Modo B: Directo al agente (bypass orquestador)

```http
POST /api/v1/chat
Content-Type: application/json

{
  "user_id": "demo-user-id",
  "message": "¿Cómo soluciono un atasco de papel?",
  "agent_id": "{agent_id}",
  "session_id": "{session_id}",
  "tenant_id": 1
}
```

---

## Paso 4 — Respuesta con Fuentes

**Respuesta (200 OK):**
```json
{
  "message_id": "m1n2o3p4-...",
  "session_id": "s1t2u3v4-...",
  "answer": "El cartucho de tóner HP 58X (CF258X) es el de alta capacidad, con un rendimiento de aproximadamente 10,000 páginas. Para uso estándar, el HP 58A (CF258A) rinde ~3,000 páginas.",
  "agent_used": {
    "id": "a1b2c3d4-...",
    "name": "HP LaserJet Expert",
    "topic": "Impresoras HP LaserJet"
  },
  "sources": [
    {
      "document_id": "d1e2f3g4-...",
      "filename": "hp_laserjet_manual.pdf",
      "chunk_index": 2,
      "page_from": 5,
      "page_to": 5,
      "score": 0.9234
    },
    {
      "document_id": "d1e2f3g4-...",
      "filename": "hp_laserjet_manual.pdf",
      "chunk_index": 3,
      "page_from": 6,
      "page_to": 6,
      "score": 0.8891
    }
  ],
  "prompt_tokens": 856,
  "completion_tokens": 124,
  "routing_reason": "Query is about HP printers and toner cartridges, routing to HP LaserJet Expert.",
  "error": null
}
```

---

## Verificar historial de sesión

```http
GET /api/v1/chat/sessions/{session_id}
```

```json
{
  "session": {
    "id": "s1t2u3v4-...",
    "title": "¿Cuál es el cartucho de tóner...",
    "is_active": true
  },
  "messages": [
    {
      "role": "user",
      "content": "¿Cuál es el cartucho de tóner de alta capacidad recomendado?",
      "sources": []
    },
    {
      "role": "assistant",
      "content": "El cartucho HP 58X (CF258X)...",
      "agent_name": "HP LaserJet Expert",
      "sources": [...],
      "prompt_tokens": 856,
      "completion_tokens": 124
    }
  ]
}
```

---

## Casos Límite Verificados

| Escenario | Comportamiento esperado |
|-----------|------------------------|
| Query sin agente matching | Orquestador retorna `NONE`, respuesta de "no encontré agente" |
| Query ambigua | Orquestador retorna `UNCLEAR`, pide aclaración |
| Pinecone retorna 0 chunks | Agente responde honestamente "sin información" |
| `agent_id` en request | Bypass directo, sin routing LLM |
| Documento aún en `processing` | El namespace aún no tiene vectores; Pinecone retorna [] |
| Documento `failed` | Error registrado en SQL; agente responde sin contexto |

---

## ✅ Estado de Fase 8

- [x] Crear agente — `POST /api/v1/agents`
- [x] Subir documento — `POST /api/v1/agents/{id}/documents`
- [x] Hacer consulta — `POST /api/v1/chat` (orquestador + directo)
- [x] Respuesta con fuentes — `sources[]` con score, filename, chunk_index, páginas
