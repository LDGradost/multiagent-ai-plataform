PROJECT CONTEXT – MULTI-AGENT AI PLATFORM
🎯 Objetivo del sistema

Construir una plataforma multiagente donde:

Los usuarios puedan crear agentes desde una interfaz (UI)
Cada agente represente un dominio de conocimiento específico
Los usuarios puedan subir documentos y asignarlos a un agente
Los documentos se procesen y se conviertan en embeddings usando Google Gemini Embedding 2
Los embeddings se almacenen en Pinecone
Las consultas se respondan usando Amazon Bedrock
Exista un agente orquestador que determine qué agente debe responder
🏗️ Arquitectura general

Flujo principal:

Frontend → FastAPI → Orchestrator →
→ Pinecone (vector search)
→ Google Embeddings (query)
→ Bedrock (respuesta)

⚙️ Stack tecnológico (obligatorio)
Backend: Python + FastAPI
Base de datos: PostgreSQL
Storage: S3 o compatible
Embeddings: Google Gemini Embedding 2
Vector DB: Pinecone
LLM (chat): Amazon Bedrock
Agentes: LangChain + LangGraph
🧩 Conceptos clave
Agent

Entidad que representa un dominio de conocimiento.

Cada agente tiene:

id
user_id
name
description
topic
system_prompt
pinecone_namespace
embedding_model
llm_model
Knowledge Base
Cada agente tiene una base de conocimiento lógica
NO se crea un índice por agente
Se usa un índice compartido en Pinecone
Cada agente usa un namespace
🧱 Estrategia de namespaces (Pinecone)

Formato obligatorio:

tenant_{tenant_id}_user{user_id}_agent{agent_id}

Ejemplo:
tenant_1__user_45__agent_900

📦 Flujo del sistema
1. Crear agente
Se guarda en PostgreSQL
Se genera namespace único
Se asocia al agente
NO se crea índice nuevo en Pinecone
2. Subir documentos

Flujo:

Usuario sube archivo
Selecciona agente destino
Backend:
guarda archivo en storage
crea registro en SQL
procesa documento:
extracción de texto
chunking
embeddings (Google)
upsert en Pinecone (namespace del agente)
Documento queda en estado "ready" o "failed"
3. Consulta (chat)

Flujo:

Usuario envía mensaje
Orchestrator analiza intención
Determina agente adecuado
Se obtiene namespace del agente
Se genera embedding de la query
Se consulta Pinecone SOLO en ese namespace
Se recuperan chunks relevantes
Se construye contexto
Se envía a Bedrock
Se devuelve:
respuesta
fuentes
🧠 Orchestrator (Agente supervisor)

Debe:

analizar intención del usuario
seleccionar el agente correcto
delegar la consulta

No debe:

consultar todos los namespaces
mezclar conocimiento de agentes
🤖 Agentes especializados

Cada agente:

responde solo con su base de conocimiento
no inventa información
usa RAG (retrieval + generación)
🧾 Metadata de vectores (Pinecone)

Cada vector debe incluir:

chunk_id
document_id
agent_id
filename
text
chunk_index
page_from
page_to
created_at
🗄️ Base de datos (estructura mínima)
agents
id
user_id
name
description
topic
system_prompt
pinecone_namespace
embedding_model
llm_model
created_at
documents
id
agent_id
user_id
file_name
storage_path
mime_type
status (uploaded, processing, ready, failed)
uploaded_at
document_chunks
id
document_id
agent_id
chunk_index
vector_id
chat_sessions
id
user_id
agent_id
created_at
chat_messages
id
session_id
role
content
sources_json
created_at
⚠️ Reglas críticas (NO romper)
❌ No crear un índice Pinecone por agente
❌ No mezclar embeddings de distintos modelos
❌ No consultar múltiples agentes sin orquestador
❌ No enviar documentos completos al LLM
✅ Usar SIEMPRE el mismo modelo de embeddings
✅ Usar namespace por agente
✅ Usar RAG (no prompting directo sin contexto)
✅ Guardar archivos originales
🔌 Integraciones
Google Embeddings
Modelo: gemini-embedding-002
Uso: indexación + consulta
Dimensión: 3072
Pinecone
1 índice compartido
Namespaces por agente
Búsqueda por similitud
Amazon Bedrock
Solo generación
Prompt estructurado
Parámetros configurables
🧪 Requisitos de calidad
Código modular
Separación por capas
Manejo de errores
Logging
Variables de entorno
Código extensible
🚀 Objetivo final

Sistema donde:

Se puedan crear agentes dinámicamente
Cada agente tenga su conocimiento aislado
El orquestador enrute correctamente
Las respuestas estén basadas en documentos
El sistema sea escalable y mantenible