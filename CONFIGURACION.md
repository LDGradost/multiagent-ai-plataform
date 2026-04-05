# ✅ Guía de Configuración Completa
## Multi-Agent AI Platform — Todo lo que necesitas para que funcione

---

## RESUMEN RÁPIDO

Para que la aplicación esté 100% operativa necesitas:

| # | Qué configurar | Dónde obtenerlo | Obligatorio |
|---|---------------|-----------------|-------------|
| 1 | **PostgreSQL** — base de datos local | Instalar localmente | ✅ Sí |
| 2 | **AWS Credentials** — Bedrock + S3 | Consola AWS | ✅ Sí |
| 3 | **Google Service Account** — Embeddings | Google Cloud Console | ✅ Sí |
| 4 | **Pinecone API Key + Índice** | app.pinecone.io | ✅ Sí |
| 5 | **Python + entorno virtual** | python.org | ✅ Sí |
| 6 | **CORS + frontend** | Solo cambiar .env | ⚡ Ajuste |

---

## PASO 1 — Instalar Python 3.11+

```powershell
# Verifica tu versión (necesitas 3.11 o superior)
python --version

# Si no tienes Python 3.11:
# Descargar desde https://www.python.org/downloads/
# ⚠️ Marcar "Add Python to PATH" durante la instalación
```

---

## PASO 2 — Crear el entorno virtual e instalar dependencias

```powershell
# Ir al directorio del proyecto
cd "c:\Users\Trabajo 911\OneDrive\Desktop\Proyecto final"

# Crear entorno virtual
python -m venv .venv

# Activar (Windows PowerShell)
.venv\Scripts\Activate.ps1

# Si da error de "execution policy":
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

# Instalar todas las dependencias
pip install -e ".[dev]"
```

---

## PASO 3 — Configurar PostgreSQL

### 3.1 Instalar PostgreSQL (si no lo tienes)
```
Descargar desde: https://www.postgresql.org/download/windows/
Versión recomendada: PostgreSQL 15 o 16
Durante la instalación anota: usuario=postgres, contraseña=la que elijas
```

### 3.2 Crear la base de datos
```sql
-- Conéctate con psql o pgAdmin y ejecuta:

CREATE USER multiagent_user WITH PASSWORD 'TuPassword123';
CREATE DATABASE multiagent_db OWNER multiagent_user;
GRANT ALL PRIVILEGES ON DATABASE multiagent_db TO multiagent_user;
```

### 3.3 URL de conexión para .env
```
DATABASE_URL=postgresql+asyncpg://multiagent_user:TuPassword123@localhost:5432/multiagent_db
```
> Las tablas se crean automáticamente al iniciar el servidor en modo `development`.

---

## PASO 4 — Configurar Amazon Web Services (AWS)

Necesitas AWS para **dos servicios**:
- **Amazon Bedrock** → el LLM que genera las respuestas (Claude)
- **Amazon S3** → almacena los archivos subidos (PDFs, etc.)

### 4.1 Crear cuenta AWS (si no tienes)
```
https://aws.amazon.com/
```

### 4.2 Crear un usuario IAM con los permisos necesarios

Ve a: **IAM → Users → Create User**

Nombre de usuario: `multiagent-platform-user`

Permisos necesarios (política JSON):
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "BedrockAccess",
      "Effect": "Allow",
      "Action": [
        "bedrock:InvokeModel",
        "bedrock:InvokeModelWithResponseStream"
      ],
      "Resource": "*"
    },
    {
      "Sid": "S3Access",
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:GetObject",
        "s3:DeleteObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::multiagent-documents",
        "arn:aws:s3:::multiagent-documents/*"
      ]
    }
  ]
}
```

### 4.3 Crear Access Key
Ve a: **IAM → Users → tu-usuario → Security credentials → Create access key**

Usa el caso de uso: "Application running outside AWS"

Guarda los valores:
```
AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE
AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
```

### 4.4 Habilitar modelos en Amazon Bedrock
Ve a: **AWS Console → Amazon Bedrock → Model access → Manage model access**

Habilitar estos modelos (puede tardar unos minutos):
- ✅ `Anthropic Claude 3.5 Sonnet` (para agentes)
- ✅ `Anthropic Claude 3 Haiku` (para el orquestador, más barato)

> ⚠️ **Región importante**: Amazon Bedrock está disponible en **us-east-1** (Virginia) y **us-west-2** (Oregon). Asegúrate de estar en esa región.

### 4.5 Crear bucket S3

Ve a: **S3 → Create bucket**

```
Nombre: multiagent-documents
Región: us-east-1
Bloquear acceso público: ✅ Sí (mantener privado)
```

---

## PASO 5 — Configurar Google Cloud (Gemini Embeddings)

### 5.1 Crear proyecto en Google Cloud
```
https://console.cloud.google.com/
→ New Project → Nombre: "multiagent-ai-platform"
```

### 5.2 Habilitar la API de Vertex AI
```
APIs & Services → Enable APIs → buscar "Vertex AI API" → Enable
```

### 5.3 Crear Service Account
```
IAM & Admin → Service Accounts → Create Service Account

Nombre: multiagent-embeddings
Role: "Vertex AI User"

→ Keys → Add Key → JSON
→ Descargar el archivo JSON (ej: multiagent-key.json)
→ Guardar en: c:\Users\Trabajo 911\OneDrive\Desktop\Proyecto final\credentials\gcp-key.json
```

### 5.4 Variable de entorno
```
GOOGLE_APPLICATION_CREDENTIALS=c:/Users/Trabajo 911/OneDrive/Desktop/Proyecto final/credentials/gcp-key.json
GOOGLE_CLOUD_PROJECT=tu-project-id-de-gcp
```

> El **project ID** lo ves en la consola de GCP en la parte superior izquierda (ej: `my-project-123456`)

---

## PASO 6 — Configurar Pinecone

### 6.1 Crear cuenta
```
https://app.pinecone.io/
Plan gratuito (Starter) es suficiente para desarrollo.
```

### 6.2 Crear el índice
Ve a: **Indexes → Create Index**

```
Index name: multiagent-knowledge
Dimensions:  3072         ← debe coincidir con EMBEDDING_DIMENSION
Metric:      cosine
Cloud:       AWS
Region:      us-east-1
```

> ⚠️ **Dimensión crítica**: Si usas `gemini-embedding-2-preview` (Google) → dimensión = **3072**.
> Si usas `gemini-embedding-exp-03-07` → dimensión = **3072**. Deben coincidir exactamente.

### 6.3 Obtener API Key
```
API Keys → Create API Key → Copiar el valor
```

---

## PASO 7 — Crear el archivo .env

Crea el archivo `.env` en la raíz del proyecto:

```
c:\Users\Trabajo 911\OneDrive\Desktop\Proyecto final\.env
```

Contenido completo (reemplaza los valores `TU_*`):

```env
# ── App ──────────────────────────────────────────────────────────────────
APP_ENV=development
APP_NAME="Multi-Agent AI Platform"
APP_VERSION=1.0.0
SECRET_KEY=cambia-esto-por-una-cadena-aleatoria-32chars
DEBUG=true
LOG_LEVEL=INFO

# ── API ──────────────────────────────────────────────────────────────────
API_HOST=0.0.0.0
API_PORT=8000
API_PREFIX=/api/v1
CORS_ORIGINS=["http://localhost:3000","http://localhost:8000","null"]

# ── PostgreSQL ────────────────────────────────────────────────────────────
DATABASE_URL=postgresql+asyncpg://multiagent_user:TU_PASSWORD_POSTGRES@localhost:5432/multiagent_db

# ── Amazon Bedrock ────────────────────────────────────────────────────────
AWS_ACCESS_KEY_ID=TU_AWS_ACCESS_KEY_ID
AWS_SECRET_ACCESS_KEY=TU_AWS_SECRET_ACCESS_KEY
AWS_REGION=us-east-1
BEDROCK_DEFAULT_MODEL_ID=anthropic.claude-3-5-sonnet-20241022-v2:0
BEDROCK_ORCHESTRATOR_MODEL_ID=anthropic.claude-3-haiku-20240307-v1:0
BEDROCK_MAX_TOKENS=4096
BEDROCK_TEMPERATURE=0.1

# ── Amazon S3 ─────────────────────────────────────────────────────────────
S3_BUCKET_NAME=multiagent-documents
S3_REGION=us-east-1
S3_PREFIX=uploads/

# ── Google Vertex AI (Embeddings) ─────────────────────────────────────────
GOOGLE_APPLICATION_CREDENTIALS=c:/Users/Trabajo 911/OneDrive/Desktop/Proyecto final/credentials/gcp-key.json
GOOGLE_CLOUD_PROJECT=TU_GCP_PROJECT_ID
GOOGLE_CLOUD_LOCATION=us-central1
GOOGLE_EMBEDDING_MODEL=text-embedding-004
EMBEDDING_DIMENSION=3072

# ── Pinecone ──────────────────────────────────────────────────────────────
PINECONE_API_KEY=TU_PINECONE_API_KEY
PINECONE_INDEX_NAME=multiagent-knowledge
PINECONE_CLOUD=aws
PINECONE_REGION=us-east-1

# ── Procesamiento de documentos ───────────────────────────────────────────
CHUNK_SIZE=1000
CHUNK_OVERLAP=200
MAX_FILE_SIZE_MB=50
ALLOWED_EXTENSIONS=["pdf","docx","txt","md"]
OCR_ENABLED=false

# ── Multi-tenancy ─────────────────────────────────────────────────────────
DEFAULT_TENANT_ID=1

# ── Background tasks ──────────────────────────────────────────────────────
BACKGROUND_WORKER=fastapi
```

---

## PASO 8 — Agregar origins del frontend al CORS

La UI está en `frontend/index.html` y se abre directamente desde el sistema de archivos.
El navegador la sirve como `file://` o `null` origin. Debes permitir esto:

```env
CORS_ORIGINS=["http://localhost:3000","http://localhost:8000","null","*"]
```

O si usas un servidor local simple para la UI:
```powershell
# Opción: servir el frontend con Python (desde la carpeta frontend/)
cd "c:\Users\Trabajo 911\OneDrive\Desktop\Proyecto final\frontend"
python -m http.server 3000
# Luego abrir: http://localhost:3000
```

---

## PASO 9 — Arrancar el servidor

```powershell
# Desde la raíz del proyecto, con el venv activado:
cd "c:\Users\Trabajo 911\OneDrive\Desktop\Proyecto final"
.venv\Scripts\Activate.ps1

uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Salida esperada:
```
INFO  Starting application name=Multi-Agent AI Platform env=development
INFO  Database tables verified / created
INFO  Application startup complete.
INFO  Uvicorn running on http://0.0.0.0:8000
```

---

## PASO 10 — Verificar que todo funciona

### 10.1 Health check
```
http://localhost:8000/health
```

### 10.2 Swagger UI (documentación interactiva)
```
http://localhost:8000/docs
```

### 10.3 Abrir la UI
```
Abrir: c:\Users\Trabajo 911\OneDrive\Desktop\Proyecto final\frontend\index.html
O servir con Python en: http://localhost:3000
```

---

## COSTOS ESTIMADOS (referencia)

| Servicio | Plan | Costo aprox. desarrollo |
|----------|------|------------------------|
| **Pinecone** | Starter (gratuito) | $0/mes |
| **AWS Bedrock - Claude Haiku** | Pago por uso | ~$0.25 / 1M tokens input |
| **AWS Bedrock - Claude 3.5 Sonnet** | Pago por uso | ~$3 / 1M tokens input |
| **Google Vertex AI Embeddings** | Pago por uso | ~$0.02 / 1M chars |
| **AWS S3** | Pago por uso | ~$0.023 / GB/mes |
| **PostgreSQL** | Local | $0 |
| **Total desarrollo ligero** | | **< $5/mes** |

---

## CHECKLIST FINAL

```
[ ] Python 3.11+ instalado
[ ] Entorno virtual creado y dependencias instaladas (pip install -e ".[dev]")
[ ] PostgreSQL corriendo con la base de datos creada
[ ] Archivo .env creado con todos los valores reales
[ ] AWS: usuario IAM con permisos Bedrock + S3, access key generado
[ ] AWS: modelos Claude habilitados en Bedrock (región us-east-1)
[ ] AWS: bucket S3 "multiagent-documents" creado
[ ] Google Cloud: Service Account con rol "Vertex AI User"
[ ] Google Cloud: archivo JSON descargado en /credentials/
[ ] Pinecone: cuenta creada, índice "multiagent-knowledge" con 3072 dims
[ ] Pinecone: API key copiada al .env
[ ] uvicorn corriendo en puerto 8000
[ ] http://localhost:8000/health responde {"status": "ok"}
[ ] frontend/index.html abre y conecta al API (indicador verde "API Online")
```

---

## SOLUCIÓN DE PROBLEMAS FRECUENTES

| Error | Causa | Solución |
|-------|-------|----------|
| `asyncpg: password authentication failed` | DATABASE_URL incorrecta | Verificar usuario/contraseña PostgreSQL |
| `botocore.exceptions.NoCredentialsError` | AWS keys vacías o incorrectas | Revisar AWS_ACCESS_KEY_ID y AWS_SECRET_ACCESS_KEY en .env |
| `AccessDeniedException` en Bedrock | Modelo no habilitado | Ir a Bedrock → Model access → habilitar Claude |
| `google.auth.exceptions.DefaultCredentialError` | GOOGLE_APPLICATION_CREDENTIALS incorrecto | Verificar ruta al archivo JSON, usar slash `/` no backslash `\` |
| `pinecone.exceptions.UnauthorizedException` | PINECONE_API_KEY incorrecto | Verificar API key en app.pinecone.io |
| `Dimension mismatch` en Pinecone | EMBEDDING_DIMENSION ≠ dimensión del índice | Recrear el índice con la dimensión correcta (3072) |
| CORS error en la UI (browser console) | `null` origin no permitido | Agregar `"null"` o `"*"` a CORS_ORIGINS en .env |
| `ModuleNotFoundError` | Venv no activado o pip no corrió | `.venv\Scripts\Activate.ps1` y `pip install -e ".[dev]"` |
