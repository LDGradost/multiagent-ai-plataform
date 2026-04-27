# 🗂️ Estructura del Proyecto — Guía de Archivos y Carpetas

> Cada subcarpeta de `app/` representa una **capa de la arquitectura limpia**.
> Las capas de arriba solo dependen de las de abajo. Nunca al revés.

---

## Estructura general

```
app/
├── main.py                  ← Punto de entrada de la aplicación FastAPI
├── core/                    ← Configuración, logging, excepciones, DI
├── domain/                  ← Entidades de negocio e interfaces (contratos)
├── application/             ← Casos de uso / lógica de negocio
├── agents/                  ← Orquestación LangGraph + nodos de agente
├── api/                     ← Rutas HTTP y manejo de errores
├── infrastructure/          ← Implementaciones externas (DB, AWS, Google, Pinecone)
└── schemas/                 ← DTOs Pydantic de request/response para la API
```

---

## `main.py` — Punto de entrada

**Qué hace:** Crea y configura la aplicación FastAPI completa.

| Responsabilidad | Detalle |
|-----------------|---------|
| `create_app()` | Instancia FastAPI, registra middleware CORS, incluye el router principal, registra exception handlers |
| `lifespan()` | Función async de startup/shutdown: configura logging, crea tablas SQL en modo `development`, cierra el pool de conexiones al apagar |
| `app = create_app()` | La instancia global que uvicorn ejecuta |

> **En producción:** las tablas se crean con Alembic, no automáticamente.

---

## `core/` — Núcleo transversal

Contiene todo lo que el resto de la aplicación necesita para funcionar: configuración, logs, errores y dependencias.

```
core/
├── config.py         ← Variables de entorno + validación
├── logging.py        ← Configuración de structlog
├── exceptions.py     ← Jerarquía de errores tipados
└── dependencies.py   ← Contenedor de Inyección de Dependencias (DI)
```

---

### `core/config.py`

**Qué hace:** Lee **todas** las variables de entorno del archivo `.env` y las expone como un objeto Python tipado.

**Cómo funciona:**
- Usa `pydantic-settings` para validar cada variable al arrancar
- Si falta una variable obligatoria o tiene un valor inválido → la app no arranca (fail-fast)
- Implementa `@lru_cache` para que solo se lea `.env` una vez (singleton)

**Variables que gestiona:** DATABASE_URL, AWS credentials, Pinecone API key, Google Cloud project, modelos de Bedrock, parámetros de chunking, CORS origins, etc.

**Uso en el código:**
```python
from app.core.config import settings
print(settings.pinecone_api_key)
```

---

### `core/logging.py`

**Qué hace:** Configura `structlog` para generar logs estructurados en formato JSON.

**Por qué structlog:** A diferencia del `logging` estándar de Python, structlog produce logs con campos clave-valor (JSON), lo que facilita filtrarlos en herramientas como CloudWatch, Datadog o ELK.

**Ejemplo de log generado:**
```json
{"event": "Agent created", "agent_id": "abc123", "user_id": "demo-user-id", "level": "info"}
```

**Uso en el código:**
```python
from app.core.logging import get_logger
logger = get_logger(__name__)
logger.info("Documento procesado", doc_id=doc.id, chunks=12)
```

---

### `core/exceptions.py`

**Qué hace:** Define la jerarquía completa de errores de negocio del sistema.

**Clases de error definidas:**

| Excepción | HTTP Status | Cuándo se lanza |
|-----------|-------------|-----------------|
| `PlatformError` | — | Clase base de todos los errores |
| `AgentNotFoundError` | 404 | El agente solicitado no existe |
| `DocumentNotFoundError` | 404 | El documento no existe |
| `ChatSessionNotFoundError` | 404 | La sesión de chat no existe |
| `FileTooLargeError` | 413 | El archivo supera `MAX_FILE_SIZE_MB` |
| `UnsupportedFileTypeError` | 415 | Extensión de archivo no permitida |
| `VectorStoreError` | 500 | Error al interactuar con Pinecone |
| `EmbeddingError` | 500 | Error al generar embeddings con Google |
| `LLMError` | 500 | Error al llamar a Amazon Bedrock |
| `StorageError` | 500 | Error al subir/descargar de S3 |

---

### `core/dependencies.py`

**Qué hace:** Define el **contenedor de Inyección de Dependencias (DI)** para FastAPI.

**Cómo funciona:** Cada dependencia es una función `async` que FastAPI invoca automáticamente al recibir un request. Los clientes externos (Pinecone, Bedrock, Google) se crean como **singletons** en el startup y se reutilizan en todos los requests.

**Type aliases definidos** (para usar con `Depends` en los endpoints):

```python
AgentRepoDep       → repositorio de agentes (PostgreSQL)
KBRepoDep          → repositorio de knowledge bases
DocumentRepoDep    → repositorio de documentos
ChunkRepoDep       → repositorio de chunks
ChatSessionRepoDep → repositorio de sesiones de chat
ChatMessageRepoDep → repositorio de mensajes
EmbeddingClientDep → cliente de Google Embeddings
PineconeClientDep  → cliente de Pinecone
BedrockClientDep   → cliente de Amazon Bedrock
S3ClientDep        → cliente de Amazon S3
ParserRegistryDep  → registro de parsers de documentos
```

**Ejemplo de uso en un endpoint:**
```python
async def create_agent(agent_repo: AgentRepoDep, kb_repo: KBRepoDep):
    # FastAPI inyecta automáticamente los repositorios
    ...
```

---

## `domain/` — Capa de Dominio

**Regla de oro:** Esta capa NO importa nada de FastAPI, SQLAlchemy, boto3, ni ningún framework externo. Solo Python puro.

```
domain/
├── entities/
│   └── entities.py        ← Dataclasses de negocio
└── interfaces/
    └── repositories.py    ← Contratos abstractos de repositorios
```

---

### `domain/entities/entities.py`

**Qué hace:** Define los objetos de negocio del sistema como **dataclasses Python puras**.

**Entidades definidas:**

| Entidad | Descripción |
|---------|-------------|
| `Agent` | Agente de IA: tiene nombre, tema, system prompt, namespace Pinecone, modelo LLM |
| `KnowledgeBase` | Base de conocimiento lógica de un agente: estadísticas de docs y chunks en Pinecone |
| `Document` | Archivo subido: nombre, ruta S3, estado (uploaded/processing/ready/failed), chunks totales |
| `DocumentChunk` | Un fragmento de texto de un documento: índice, vector_id en Pinecone, páginas |
| `ChatSession` | Sesión de conversación: usuario, agente, título, activa/inactiva |
| `ChatMessage` | Mensaje individual: rol (user/assistant), contenido, fuentes, tokens consumidos |
| `ChatSource` | Fuente de información retornada con cada respuesta: archivo, chunk, score de relevancia |
| `User` | Usuario del sistema (para multi-tenant futuro) |

**Enums:**
- `DocumentStatus` → `uploaded | processing | ready | failed`
- `ChatMessageRole` → `user | assistant | system`

---

### `domain/interfaces/repositories.py`

**Qué hace:** Define los **contratos abstractos** (interfaces) que toda implementación de base de datos debe cumplir.

**Por qué existen:** Siguiendo el principio de inversión de dependencias, los servicios de negocio dependen de estas interfaces, no de SQLAlchemy. Esto permite cambiar PostgreSQL por MongoDB u otra DB sin tocar la lógica de negocio.

**Interfaces definidas:**

| Interfaz | Métodos principales |
|----------|---------------------|
| `IAgentRepository` | `create`, `get_by_id`, `list_by_user`, `update`, `delete`, `list_all_active` |
| `IKnowledgeBaseRepository` | `create`, `get_by_agent_id`, `update_counts` |
| `IDocumentRepository` | `create`, `get_by_id`, `list_by_agent`, `update_status`, `update_after_processing`, `delete` |
| `IDocumentChunkRepository` | `bulk_create`, `list_by_document`, `delete_by_document` |
| `IChatSessionRepository` | `create`, `get_by_id`, `list_by_user` |
| `IChatMessageRepository` | `create`, `list_by_session` |
| `IUserRepository` | `get_by_id`, `get_by_email`, `create` |

---

## `application/` — Capa de Aplicación (Casos de Uso)

**Qué hace:** Contiene la **lógica de negocio orquestada**. Cada servicio representa un caso de uso completo del sistema.

```
application/
├── dtos/             ← (vacío por ahora — los DTOs viven en schemas/)
└── services/
    ├── create_agent_service.py
    ├── upload_document_service.py
    ├── vector_ingestion_service.py
    ├── search_knowledge_service.py
    ├── chat_orchestration_service.py
    └── delete_document_service.py
```

---

### `application/services/create_agent_service.py`

**Qué hace:** Caso de uso para **crear un nuevo agente**.

**Pasos que ejecuta:**
1. Genera el namespace Pinecone con el formato: `tenant_{id}_user_{user_id}_agent_{agent_id}`
2. Persiste el `Agent` en PostgreSQL
3. Crea el registro `KnowledgeBase` asociado (sin crear ningún índice en Pinecone)
4. Retorna el agente creado con su knowledge base

**Importante:** No crea nada en Pinecone. El namespace es solo un string lógico hasta que se sube el primer documento.

---

### `application/services/upload_document_service.py`

**Qué hace:** Caso de uso para **subir un archivo y disparar su procesamiento** en background.

**Pasos que ejecuta:**
1. Valida que el agente exista y que el archivo sea del tipo permitido
2. Sube el archivo binario a **Amazon S3** (ruta: `uploads/{user_id}/{agent_id}/{filename}`)
3. Crea el registro `Document` en PostgreSQL con `status = "uploaded"`
4. Encola el pipeline de procesamiento como **BackgroundTask** de FastAPI
5. Retorna inmediatamente con HTTP 202 (el procesamiento continúa en background)

**El pipeline de background llama a:** `VectorIngestionService`

---

### `application/services/vector_ingestion_service.py`

**Qué hace:** Pipeline completo de **ingesta de documentos a Pinecone**.

**Pasos que ejecuta (en background):**
1. Actualiza `status = "processing"` en PostgreSQL
2. Descarga el archivo de S3
3. Extrae el texto con el parser adecuado (PDF, DOCX, TXT, Markdown)
4. Divide el texto en chunks usando `RecursiveCharacterTextSplitter` (LangChain)
5. Genera embeddings de todos los chunks con **Google Gemini** (`text-embedding-004`)
6. Sube los vectores a **Pinecone** en el namespace del agente, con metadata completa
7. Persiste los `DocumentChunk` en PostgreSQL
8. Actualiza contadores en `KnowledgeBase`
9. Actualiza `status = "ready"` (o `"failed"` si algo falla)

---

### `application/services/search_knowledge_service.py`

**Qué hace:** Servicio de **búsqueda semántica** en el namespace de un agente.

**Pasos que ejecuta:**
1. Genera el embedding de la query con **Google Gemini**
2. Consulta **Pinecone** en el namespace del agente (`top_k=5` por defecto)
3. Retorna los chunks más relevantes con su score de similitud coseno

**Uso:** Es llamado por el `SpecializedAgentNode` durante el chat RAG.

---

### `application/services/chat_orchestration_service.py`

**Qué hace:** Caso de uso de **chat completo** (alternativa sin LangGraph para casos simples).

Implementa el flujo:
1. Crear o recuperar sesión de chat en PostgreSQL
2. Si viene `agent_id` → ir directo al agente
3. Si no → llamar al routing de Bedrock para seleccionar agente
4. Ejecutar búsqueda semántica en Pinecone
5. Construir prompt con contexto RAG
6. Llamar a Bedrock (Claude) para generar respuesta
7. Persistir mensaje de usuario y respuesta del asistente
8. Retornar respuesta con fuentes y tokens usados

> **Nota:** En el flujo principal del proyecto se usa `AgentGraphService` (LangGraph). Este servicio es una alternativa más simple.

---

### `application/services/delete_document_service.py`

**Qué hace:** Caso de uso para **eliminar un documento** completamente del sistema.

**Pasos que ejecuta:**
1. Recupera el documento y sus chunks de PostgreSQL
2. Elimina los vectores de **Pinecone** (por `vector_id` de cada chunk)
3. Actualiza los contadores de `KnowledgeBase` (resta documentos y chunks)
4. Elimina el archivo de **Amazon S3**
5. Elimina los `DocumentChunk` de PostgreSQL
6. Elimina el `Document` de PostgreSQL

---

## `agents/` — Orquestación LangGraph

**Qué hace:** Implementa el sistema de agentes con LangGraph. Es el "cerebro" del sistema.

```
agents/
├── graph/
│   ├── state.py                  ← Estado tipado del grafo
│   ├── prompts.py                ← Todos los prompts del sistema
│   ├── orchestrator_graph.py     ← Construcción del StateGraph dinámico
│   └── agent_graph_service.py   ← Fachada: FastAPI → LangGraph
├── orchestrator/
│   └── supervisor_node.py        ← Nodo que decide qué agente usar
└── specialized/
    └── specialized_agent_node.py ← Nodo que ejecuta RAG + Bedrock
```

---

### `agents/graph/state.py`

**Qué hace:** Define `AgentState`, el objeto tipado que fluye entre todos los nodos del grafo.

**Campos del estado:**

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `messages` | `list[BaseMessage]` | Historial de conversación (LangChain). El reducer `add_messages` lo acumula automáticamente |
| `user_query` | `str` | Texto exacto de la consulta del usuario |
| `agent_id` | `str?` | Si viene de la request, el grafo salta el routing |
| `selected_agent` | `Agent?` | Entidad del agente elegido por el supervisor |
| `routing_reason` | `str?` | Explicación en texto de por qué se eligió ese agente |
| `context_chunks` | `list` | Resultados de Pinecone (texto + metadata de cada chunk) |
| `sources` | `list[ChatSource]` | Fuentes formateadas para incluir en la respuesta final |
| `final_answer` | `str?` | Texto de la respuesta generada por Bedrock |
| `prompt_tokens` | `int` | Tokens de entrada usados en Bedrock |
| `completion_tokens` | `int` | Tokens de salida generados por Bedrock |
| `next_node` | `str` | Campo de control: el supervisor lo pone con el `agent_id` del siguiente nodo |
| `error` | `str?` | Si un nodo falla, el error se guarda aquí en lugar de romper el grafo |

---

### `agents/graph/prompts.py`

**Qué hace:** Centraliza **todos los prompts del sistema** para que sean fáciles de ajustar sin tocar lógica de código.

**Prompts definidos:**

| Constante | Usada por | Propósito |
|-----------|-----------|-----------|
| `SUPERVISOR_SYSTEM_PROMPT` | `supervisor_node.py` | Le dice a Claude Haiku que analice la consulta y elija un agente. Le pasa la lista de agentes en JSON y pide respuesta en JSON puro (`{"agent_id": "...", "reason": "..."}`) |
| `SPECIALIZED_AGENT_SYSTEM_PROMPT` | `specialized_agent_node.py` | Le dice a Claude Sonnet que responda SOLO con el contexto RAG proporcionado, sin inventar datos |
| `NO_CONTEXT_ANSWER` | `specialized_agent_node.py` | Respuesta cuando Pinecone no retorna chunks relevantes |
| `UNCLEAR_ROUTING_ANSWER` | `orchestrator_graph.py` | Respuesta cuando el supervisor no puede decidir entre varios agentes |
| `NO_AGENT_ANSWER` | `orchestrator_graph.py` | Respuesta cuando ningún agente es apropiado para la consulta |

---

### `agents/graph/orchestrator_graph.py`

**Qué hace:** Construye el **StateGraph de LangGraph** de forma dinámica según los agentes existentes en la DB.

**Cómo funciona:**
1. Carga todos los agentes activos de PostgreSQL al arrancar
2. Por cada agente, registra un nodo `{agent_id}_node` en el grafo
3. El nodo supervisor decide a qué nodo ir (usando `next_node` del estado)
4. Los edges condicionales (`add_conditional_edges`) dirigen el flujo según la decisión del supervisor
5. El grafo se compila una vez y se reutiliza (es stateless internamente — el estado va en `AgentState`)

**Flujo del grafo:**
```
[START] → supervisor_node → (condicional) → specialized_agent_node_{X} → [END]
                                          → "NONE"  → respuesta vacía   → [END]
                                          → "UNCLEAR" → respuesta ambigua → [END]
```

---

### `agents/graph/agent_graph_service.py`

**Qué hace:** Es la **fachada** que expone LangGraph al resto de la aplicación. El endpoint de chat llama esto directamente.

**Responsabilidades:**
1. Recibe `GraphChatInput` (user_id, message, session_id, agent_id, tenant_id)
2. Crea o recupera la sesión de chat en PostgreSQL
3. Construye el estado inicial `AgentState` y lo pasa al grafo compilado
4. Ejecuta el grafo con `graph.invoke(state)`
5. Toma el estado final y persiste los mensajes (usuario + asistente) en PostgreSQL
6. Retorna `GraphChatOutput` con la respuesta, fuentes, tokens y agente usado

---

### `agents/orchestrator/supervisor_node.py`

**Qué hace:** Implementa el **nodo supervisor** del grafo LangGraph.

**Pasos al ejecutarse:**
1. Carga todos los agentes activos de la DB
2. Construye el prompt `SUPERVISOR_SYSTEM_PROMPT` inyectando la lista de agentes en JSON
3. Llama a **Amazon Bedrock con Claude Haiku** (modelo más rápido y barato para routing)
4. Parsea la respuesta JSON del modelo: `{"agent_id": "...", "reason": "..."}`
5. Actualiza `state["next_node"]` con el `agent_id` elegido (o "NONE"/"UNCLEAR")

**Casos especiales:**
- Si el JSON está malformado → `next_node = "NONE"`
- Si `-agent_id` viene de la request directamente → el supervisor se saltea (no se ejecuta)

---

### `agents/specialized/specialized_agent_node.py`

**Qué hace:** Implementa el **nodo de agente especializado**. Se ejecuta uno por cada agente elegido.

**Pasos al ejecutarse:**
1. Recupera el `Agent` entity del estado (puesto por el supervisor)
2. Genera el embedding de la query con **Google Gemini** (`embed_query`)
3. Consulta **Pinecone** en el namespace del agente (`top_k=5`)
4. Si no hay chunks → retorna `NO_CONTEXT_ANSWER`
5. Construye el contexto RAG: concatena el texto de cada chunk con su fuente
6. Construye el sistema prompt usando `SPECIALIZED_AGENT_SYSTEM_PROMPT` con el contexto
7. Llama a **Amazon Bedrock** (Claude Sonnet) con el prompt completo
8. Extrae la respuesta y los tokens consumidos
9. Actualiza el estado con `final_answer`, `sources`, `prompt_tokens`, `completion_tokens`

---

## `api/` — Capa HTTP (FastAPI)

**Qué hace:** Expone los casos de uso como endpoints HTTP REST.

```
api/
├── exception_handlers.py    ← Convierte excepciones de negocio en respuestas HTTP
└── v1/
    ├── router.py            ← Agrega todos los routers con sus prefijos
    └── endpoints/
        ├── agents.py        ← CRUD de agentes
        ├── documents.py     ← Upload, lista y eliminación de documentos
        ├── chat.py          ← Envío de mensajes y consulta de sesiones
        └── health.py        ← Endpoint de health check
```

---

### `api/exception_handlers.py`

**Qué hace:** Registra handlers globales que interceptan las excepciones tipadas y las convierten en respuestas HTTP con el código correcto.

**Ejemplo:**
- `AgentNotFoundError` → `{"detail": "Agent abc123 not found"}` con HTTP 404
- `FileTooLargeError` → `{"detail": "File exceeds 50MB limit"}` con HTTP 413
- Error inesperado → `{"detail": "Internal server error"}` con HTTP 500

---

### `api/v1/router.py`

**Qué hace:** Agrega los 3 routers de endpoints bajo el prefijo `/api/v1`.

| Router | Prefijo | Tag |
|--------|---------|-----|
| `agents.router` | `/api/v1/agents` | Agents |
| `documents.router` | `/api/v1/agents` | Documents |
| `chat.router` | `/api/v1/chat` | Chat |

---

### `api/v1/endpoints/agents.py`

**Qué hace:** CRUD completo de agentes.

| Método | Ruta | Descripción |
|--------|------|-------------|
| `POST` | `/agents` | Crear agente → llama `CreateAgentService` |
| `GET` | `/agents` | Listar agentes del usuario (con filtro `active_only`) |
| `GET` | `/agents/{agent_id}` | Detalle de un agente + stats de knowledge base |
| `PATCH` | `/agents/{agent_id}` | Actualizar nombre, prompt, modelo, temperatura, etc. |
| `DELETE` | `/agents/{agent_id}` | Soft delete: pone `is_active = False` en PostgreSQL |

---

### `api/v1/endpoints/documents.py`

**Qué hace:** Gestión de documentos por agente.

| Método | Ruta | Descripción |
|--------|------|-------------|
| `POST` | `/agents/{agent_id}/documents` | Upload multipart → `UploadDocumentService` → HTTP 202 |
| `GET` | `/agents/{agent_id}/documents` | Lista todos los documentos del agente |
| `GET` | `/agents/{agent_id}/documents/{doc_id}` | Detalle de un documento y su estado de procesamiento |
| `DELETE` | `/agents/documents/{doc_id}` | Elimina documento de Pinecone + S3 + PostgreSQL |

---

### `api/v1/endpoints/chat.py`

**Qué hace:** Interfaz de chat con el sistema multi-agente.

| Método | Ruta | Descripción |
|--------|------|-------------|
| `POST` | `/chat` | Envía un mensaje → `AgentGraphService` (LangGraph) → respuesta con fuentes |
| `GET` | `/chat/sessions/{session_id}` | Historial completo de una sesión (mensajes + fuentes) |
| `GET` | `/chat/sessions` | Lista todas las sesiones del usuario |

---

### `api/v1/endpoints/health.py`

**Qué hace:** Endpoint simple de verificación de estado.

```http
GET /health
→ {"status": "ok", "version": "1.0.0"}
```

---

## `schemas/` — DTOs de la API

**Qué hace:** Define los modelos Pydantic para validar y serializar los datos de entrada (request) y salida (response) de la API. No contienen lógica — solo contratos de datos.

```
schemas/
├── agent_schemas.py       ← Schemas de agentes
├── document_schemas.py    ← Schemas de documentos
└── chat_schemas.py        ← Schemas de chat
```

---

### `schemas/agent_schemas.py`

| Schema | Tipo | Campos clave |
|--------|------|-------------|
| `AgentCreateRequest` | Request | `name`, `topic`, `system_prompt` (obligatorios); `llm_model`, `llm_temperature`, `llm_max_tokens` (opcionales) |
| `AgentUpdateRequest` | Request | Todos los campos opcionales (PATCH parcial) |
| `AgentResponse` | Response | Todos los campos del agente + objeto `knowledge_base` anidado |
| `KnowledgeBaseResponse` | Nested | `pinecone_namespace`, `total_documents`, `total_chunks`, `status` |
| `AgentListResponse` | Response | `total` + lista de `AgentResponse` |

---

### `schemas/document_schemas.py`

| Schema | Tipo | Campos clave |
|--------|------|-------------|
| `DocumentUploadResponse` | Response | `document` (detalle) + `processing_started` (bool) |
| `DocumentResponse` | Response | `id`, `file_name`, `status`, `total_chunks`, `storage_path` |
| `DocumentListResponse` | Response | `total` + lista de `DocumentResponse` |
| `DeleteResponse` | Response | `success`, `message` |

---

### `schemas/chat_schemas.py`

| Schema | Tipo | Campos clave |
|--------|------|-------------|
| `ChatRequest` | Request | `user_id`, `message` (obligatorios); `session_id`, `agent_id` (opcionales para routing manual) |
| `ChatResponse` | Response | `answer`, `agent_used`, `sources[]`, `prompt_tokens`, `completion_tokens`, `routing_reason` |
| `SourceResponse` | Nested | `filename`, `chunk_index`, `page_from`, `page_to`, `score` |
| `AgentUsedResponse` | Nested | `id`, `name`, `topic` del agente que respondió |
| `ChatSessionResponse` | Response | `id`, `title`, `is_active`, fechas |
| `ChatHistoryResponse` | Response | `session` + `messages[]` completo |
| `ChatMessageResponse` | Response | `role`, `content`, `agent_name`, `sources[]`, tokens |

---

## `infrastructure/` — Capa de Infraestructura

**Qué hace:** Implementaciones concretas de todos los servicios externos. Cada subcarpeta es un **adaptador** a un proveedor externo.

```
infrastructure/
├── db/              ← PostgreSQL (SQLAlchemy ORM + repositorios + migraciones)
├── bedrock/         ← Amazon Bedrock (LLM)
├── embeddings/      ← Google Vertex AI (embeddings)
├── pinecone/        ← Pinecone (vector DB)
├── storage/         ← Amazon S3 (archivos)
└── parsers/         ← Parsers de documentos (PDF, DOCX, TXT, MD)
```

---

### `infrastructure/db/session.py`

**Qué hace:** Crea y expone el motor SQLAlchemy async y la función `get_db_session`.

- `engine` → Motor SQLAlchemy con pool de conexiones async (asyncpg)
- `AsyncSessionLocal` → Factory de sesiones async
- `get_db_session()` → Función generadora que FastAPI usa como dependencia. Abre una sesión, la entrega, y la cierra al terminar el request (con commit o rollback automático)

---

### `infrastructure/db/models/models.py`

**Qué hace:** Define los modelos ORM de SQLAlchemy que mapean directamente a las tablas de PostgreSQL.

**Modelos ORM definidos:**

| Modelo ORM | Tabla SQL | Descripción |
|------------|-----------|-------------|
| `UserModel` | `users` | Usuarios del sistema |
| `AgentModel` | `agents` | Agentes con su configuración completa |
| `KnowledgeBaseModel` | `knowledge_bases` | Estadísticas de vectores por agente |
| `DocumentModel` | `documents` | Archivos subidos con su estado |
| `DocumentChunkModel` | `document_chunks` | Registro de cada chunk vectorizado |
| `ChatSessionModel` | `chat_sessions` | Sesiones de conversación |
| `ChatMessageModel` | `chat_messages` | Mensajes individuales con fuentes en JSON |

---

### `infrastructure/db/repositories/agent_repository.py`

**Qué hace:** Implementa `IAgentRepository` usando SQLAlchemy async.

**Operaciones:** `create`, `get_by_id`, `list_by_user`, `list_all_active`, `update`, `delete`

---

### `infrastructure/db/repositories/document_repository.py`

**Qué hace:** Implementa `IDocumentRepository` e `IDocumentChunkRepository`.

**Operaciones clave:** `create`, `update_status` (cambia uploaded→processing→ready/failed), `update_after_processing` (guarda total_chunks y modelo), `bulk_create` (inserta múltiples chunks en una transacción), `delete_by_document`

---

### `infrastructure/db/repositories/chat_repository.py`

**Qué hace:** Implementa `IChatSessionRepository` e `IChatMessageRepository`.

**Operaciones:** crear sesiones, listar por usuario, crear mensajes con `sources_json` (JSONB en PostgreSQL), listar historial de una sesión

---

### `infrastructure/db/migrations/env.py`

**Qué hace:** Configura Alembic para usar el motor async de SQLAlchemy. Permite ejecutar migraciones de esquema sin necesidad de sincronizar manualmente el modelo ORM.

**Uso:**
```powershell
alembic revision --autogenerate -m "descripción"
alembic upgrade head
```

---

### `infrastructure/db/migrations/schema_reference.sql`

**Qué hace:** Script SQL de referencia con el esquema completo de la base de datos. Incluye:
- Creación de todas las tablas con tipos, índices y constraints
- Triggers para `updated_at` automático
- Comentarios explicativos por columna
- Datos de ejemplo para desarrollo

> Es solo documentación de referencia. Las tablas se crean vía Alembic o automáticamente en modo `development`.

---

### `infrastructure/bedrock/bedrock_client.py`

**Qué hace:** Cliente para **Amazon Bedrock** (generación de texto con Claude).

**Métodos principales:**

| Método | Descripción |
|--------|-------------|
| `invoke(prompt, system, model_id, temperature, max_tokens)` | Llama al modelo Claude vía Bedrock Converse API. Retorna texto + tokens |
| `route(prompt, agents_json)` | Versión especializada para routing: llama a Claude Haiku con temperatura 0 para decisiones deterministas |

**Características:**
- Usa `tenacity` para reintentos automáticos con backoff exponencial en errores transitorios
- Soporta override de modelo y parámetros por llamada
- Extrae `usage.input_tokens` y `usage.output_tokens` de la respuesta

---

### `infrastructure/embeddings/google_embedding_client.py`

**Qué hace:** Cliente para **Google Vertex AI** (generación de embeddings con `text-embedding-004`).

**Métodos principales:**

| Método | Descripción |
|--------|-------------|
| `embed_documents(texts)` | Genera embeddings para una lista de textos (documentos). Usa `RETRIEVAL_DOCUMENT` task type. Procesa en lotes de 250 para respetar límites de la API |
| `embed_query(text)` | Genera embedding para una consulta. Usa `RETRIEVAL_QUERY` task type (diferente al de indexación) |

**Importante:** Se usan **task types diferentes** para indexación vs consulta. Esto es requerido por el modelo para obtener la mejor calidad de búsqueda semántica.

---

### `infrastructure/pinecone/pinecone_client.py`

**Qué hace:** Cliente para **Pinecone** (base de datos vectorial).

**Métodos principales:**

| Método | Descripción |
|--------|-------------|
| `upsert(vectors, namespace)` | Sube vectores con metadata al namespace del agente. Procesa en lotes de 100 |
| `query(vector, namespace, top_k, filter)` | Búsqueda de los K vectores más similares en un namespace específico |
| `delete_by_ids(ids, namespace)` | Elimina vectores específicos por su ID |
| `delete_by_document(document_id, namespace)` | Elimina todos los vectores de un documento usando filtrado por metadata |
| `get_namespace_stats(namespace)` | Retorna estadísticas del namespace: cantidad de vectores, dimensión |

**Metadata que se guarda con cada vector:**
```json
{
  "chunk_id": "...",
  "document_id": "...",
  "agent_id": "...",
  "filename": "manual.pdf",
  "text": "El texto del chunk...",
  "chunk_index": 3,
  "page_from": 5,
  "page_to": 6,
  "created_at": "2026-03-25T..."
}
```

---

### `infrastructure/storage/s3_client.py`

**Qué hace:** Cliente para **Amazon S3** (almacenamiento de archivos originales).

**Métodos principales:**

| Método | Descripción |
|--------|-------------|
| `upload(content, key, content_type)` | Sube bytes a S3 con cifrado AES256 en reposo |
| `download(key)` | Descarga el contenido de un archivo como bytes |
| `delete(key)` | Elimina un archivo de S3 |
| `delete_agent_folder(agent_id)` | Elimina todos los archivos de un agente (listado + delete batch) |
| `generate_presigned_url(key, expiry)` | Genera URL temporal firmada para descargas directas |

**Ruta de archivos en S3:** `uploads/{user_id}/{agent_id}/{filename}`

---

### `infrastructure/parsers/document_parser.py`

**Qué hace:** Registra y aplica el parser correcto según el tipo de archivo (MIME type).

**Parsers implementados:**

| Clase | Extensión | Tecnología |
|-------|-----------|-----------|
| `PdfParser` | `.pdf` | `pypdf` — extrae texto página por página, retorna texto con número de página |
| `DocxParser` | `.docx` | `python-docx` — extrae párrafos y texto de tablas |
| `TxtParser` | `.txt` | Python nativo — maneja múltiples encodings (UTF-8, Latin-1, CP1252) |
| `MarkdownParser` | `.md` | Elimina tags HTML y convierte a texto plano |

**`DocumentParserRegistry`:** Registro central que mapea MIME type → Parser. El `VectorIngestionService` lo usa para elegir el parser correcto automáticamente.

---

## Diagrama de dependencias entre capas

```
┌─────────────────────────────────────────────────────┐
│  api/                 (HTTP layer)                  │
│  endpoints → schemas → application → domain         │
└──────────────────────────┬──────────────────────────┘
                           │ usa
┌──────────────────────────▼──────────────────────────┐
│  application/             (Use Cases)               │
│  services/ → domain/interfaces/ (contratos)        │
└──────────────────────────┬──────────────────────────┘
                           │ usa
┌──────────────────────────▼──────────────────────────┐
│  agents/                  (LangGraph)               │
│  graph/ + orchestrator/ + specialized/              │
└──────────────────────────┬──────────────────────────┘
                           │ implementa contratos de
┌──────────────────────────▼──────────────────────────┐
│  infrastructure/          (Adapters)                │
│  db/ + bedrock/ + embeddings/ + pinecone/ +         │
│  storage/ + parsers/                                │
└─────────────────────────────────────────────────────┘
         ↑ Todo lo de arriba depende de:
┌─────────────────────────────────────────────────────┐
│  domain/                  (Core)                    │
│  entities/ + interfaces/                            │
│  ← NO depende de nada externo                       │
└─────────────────────────────────────────────────────┘
         ↑ Todo configura usando:
┌─────────────────────────────────────────────────────┐
│  core/                    (Cross-cutting)           │
│  config + logging + exceptions + dependencies       │
└─────────────────────────────────────────────────────┘
```
