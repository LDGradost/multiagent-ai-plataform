# 🚀 Guía de Despliegue — Multi-Agent AI Platform

---

## ⚠️ Primero: entiende qué tienes

Tu proyecto tiene **dos partes separadas** que van a plataformas diferentes:

```
┌─────────────────────────────────┐    ┌──────────────────────────────┐
│  BACKEND (Python FastAPI)       │    │  FRONTEND (HTML + CSS + JS)  │
│  app/ + main.py                 │    │  frontend/                   │
│  Necesita: Python, PostgreSQL   │    │  Son archivos estáticos puros │
│  ❌ NO va en Netlify            │    │  ✅ Perfecto para Netlify     │
│  ✅ Va en Render o Railway      │    │  ✅ También en GitHub Pages   │
└─────────────────────────────────┘    └──────────────────────────────┘
```

> **Replit** puede hacer las dos cosas, pero es menos estable para producción.
> **La combinación recomendada: Backend en Render + Frontend en Netlify**

---

## OPCIÓN A — Render (Backend) + Netlify (Frontend)
### ✅ Recomendada — Gratuita y más simple

---

### PARTE 1: Backend en Render

**Render** es la mejor opción gratuita para FastAPI con PostgreSQL incluido.

#### Paso A-1: Subir el código a GitHub

Primero necesitas tener el código en un repositorio de GitHub.

```powershell
# En la raíz del proyecto:
cd "c:\Users\Trabajo 911\OneDrive\Desktop\Proyecto final"

# Inicializar git (si no está hecho)
git init
git add .
git commit -m "feat: plataforma multi-agente completa"

# Ir a github.com → New repository → nombre: multiagent-ai-platform
# NO marques "Initialize with README" (ya tienes uno)
# Luego copia la URL y ejecuta:

git remote add origin https://github.com/TU_USUARIO/multiagent-ai-platform.git
git branch -M main
git push -u origin main
```

> ⚠️ **Antes del push**, asegúrate de que `.gitignore` incluya:
> - `.env` (nunca subas tus credenciales)
> - `.venv/`
> - `credentials/` (el archivo JSON de Google)
> - `__pycache__/`

#### Paso A-2: Crear base de datos en Render

1. Ve a **[render.com](https://render.com)** → Sign up / Log in
2. Click en **New +** → **PostgreSQL**
3. Configura:
   ```
   Name:    multiagent-db
   Region:  Oregon (US West) — o la más cercana a ti
   Plan:    Free
   ```
4. Click **Create Database**
5. Guarda el valor de **Internal Database URL** (lo necesitarás abajo)
   ```
   postgresql://multiagent_user:PASSWORD@dpg-xxx.oregon-postgres.render.com/multiagent_db
   ```
   > Para usarlo con asyncpg, cambia `postgresql://` por `postgresql+asyncpg://`

#### Paso A-3: Crear el Web Service en Render

1. **New +** → **Web Service**
2. Conecta tu repositorio de GitHub
3. Configura:
   ```
   Name:            multiagent-backend
   Region:          Oregon (US West)
   Branch:          main
   Runtime:         Python 3
   Build Command:   pip install -r requirements.txt
   Start Command:   uvicorn app.main:app --host 0.0.0.0 --port $PORT
   Plan:            Free
   ```

#### Paso A-4: Configurar variables de entorno en Render

En el panel de tu Web Service → **Environment** → agrega estas variables:

| Variable | Valor |
|----------|-------|
| `APP_ENV` | `production` |
| `DATABASE_URL` | `postgresql+asyncpg://user:pass@host/multiagent_db` ← de paso A-2 |
| `AWS_ACCESS_KEY_ID` | Tu key de AWS |
| `AWS_SECRET_ACCESS_KEY` | Tu secret de AWS |
| `AWS_REGION` | `us-east-1` |
| `BEDROCK_DEFAULT_MODEL_ID` | `anthropic.claude-3-5-sonnet-20241022-v2:0` |
| `BEDROCK_ORCHESTRATOR_MODEL_ID` | `anthropic.claude-3-haiku-20240307-v1:0` |
| `S3_BUCKET_NAME` | `multiagent-documents` |
| `S3_REGION` | `us-east-1` |
| `GOOGLE_CLOUD_PROJECT` | Tu project ID de GCP |
| `GOOGLE_CLOUD_LOCATION` | `us-central1` |
| `GOOGLE_EMBEDDING_MODEL` | `text-embedding-004` |
| `EMBEDDING_DIMENSION` | `3072` |
| `PINECONE_API_KEY` | Tu API key de Pinecone |
| `PINECONE_INDEX_NAME` | `multiagent-knowledge` |
| `PINECONE_CLOUD` | `aws` |
| `PINECONE_REGION` | `us-east-1` |
| `CHUNK_SIZE` | `1000` |
| `CHUNK_OVERLAP` | `200` |
| `MAX_FILE_SIZE_MB` | `50` |
| `CORS_ORIGINS` | `["https://TU-SITIO.netlify.app","https://TU-DOMINIO.com"]` |
| `SECRET_KEY` | Una cadena aleatoria de 32+ caracteres |
| `LOG_LEVEL` | `INFO` |

> **GOOGLE_APPLICATION_CREDENTIALS:** El archivo JSON de Google no se puede subir como archivo a Render fácilmente. Tienes dos opciones:
> - **Opción 1 (recomendada):** Copia todo el contenido JSON y ponlo en una variable llamada `GOOGLE_CREDENTIALS_JSON`. Luego modifica el cliente de embeddings para leerlo desde ahí.
> - **Opción 2:** Usa una cuenta de servicio con Workload Identity (más complejo).

#### Paso A-5: Migrar la base de datos

Al hacer el primer deploy en Render, las tablas se crearán automáticamente porque `APP_ENV=production` usa Alembic... pero como el código auto-crea en `development`, cambia `APP_ENV` temporalmente a `development` para el primer deploy, luego vuelve a `production`.

O ejecuta las migraciones desde la consola de Render:
```bash
# En Render → Shell → ejecuta:
alembic upgrade head
```

#### Tu URL del backend será:
```
https://multiagent-backend.onrender.com
```

---

### PARTE 2: Frontend en Netlify

#### Paso B-1: Actualizar la URL del backend en el frontend

Edita `frontend/index.html` — añade esta línea **antes** del `<script src="app.js">`:

```html
<!-- Producción: apunta al backend en Render -->
<script>window.API_BASE = 'https://multiagent-backend.onrender.com/api/v1';</script>
<script src="app.js"></script>
```

#### Paso B-2: Subir a Netlify (sin código)

**Forma más fácil — Drag & Drop:**

1. Ve a **[netlify.com](https://netlify.com)** → Sign up / Log in
2. En el dashboard → arrastra la carpeta `frontend/` directamente al área de deploy
3. Netlify te dará una URL en segundos:
   ```
   https://amazing-name-123abc.netlify.app
   ```

**Forma desde GitHub:**

1. Netlify **New site** → **Import from Git** → conecta GitHub
2. Configura:
   ```
   Base directory:   frontend
   Build command:    (vacío — son archivos estáticos)
   Publish directory: frontend
   ```

#### Paso B-3: Actualizar CORS en Render

Vuelve a Render → Environment → actualiza `CORS_ORIGINS`:
```
["https://amazing-name-123abc.netlify.app"]
```

---

## OPCIÓN B — Replit (Todo en uno)

**Replit** puede alojar el backend Python. Es más simple pero con limitaciones:
- ✅ Ideal para demos y prototipos
- ❌ Se "duerme" después de inactividad (plan gratuito)
- ❌ Sin PostgreSQL persistente gratuito (necesitas Supabase externo)

#### Paso B-1: Crear Repl

1. Ve a **[replit.com](https://replit.com)** → **Create Repl**
2. Elige **Python** como template
3. Importa desde GitHub o sube los archivos manualmente

#### Paso B-2: Configurar `replit.nix` para dependencias del sistema

Crea el archivo `.replit` en la raíz:

```toml
[nix]
channel = "stable-23_11"

[deployment]
run = ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]

[[ports]]
localPort = 8080
externalPort = 80
```

#### Paso B-3: Instalar dependencias

En la Shell de Replit:
```bash
pip install -r requirements.txt
```

#### Paso B-4: Variables de entorno en Replit

Ve a **Secrets** (candado 🔒 en el panel izquierdo) y agrega las mismas variables del paso A-4.

#### Paso B-5: Base de datos — usar Supabase (gratis)

Como Replit no tiene PostgreSQL gratis, conecta a **Supabase**:
1. Ve a **[supabase.com](https://supabase.com)** → New Project
2. Copia la **Connection string** (modo Session)
3. Agrega el prefijo asyncpg:
   ```
   postgresql+asyncpg://postgres:password@db.xxx.supabase.co:5432/postgres
   ```
4. Ponlo como secreto `DATABASE_URL` en Replit

---

## OPCIÓN C — Railway (Alternativa a Render)

Railway es similar a Render pero con $5 de crédito gratuito al mes.

1. Ve a **[railway.app](https://railway.app)** → New Project
2. **Deploy from GitHub repo** → selecciona tu repo
3. Railway detecta automáticamente que es Python
4. Agrega PostgreSQL: **New Service** → **Database** → **PostgreSQL**
5. La variable `DATABASE_URL` se inyecta automáticamente
6. Agrega el resto de variables de entorno en la pestaña **Variables**

---

## RESUMEN DE PLATAFORMAS

| | Render | Netlify | Replit | Railway |
|---|--------|---------|--------|---------|
| ¿Qué aloja? | Backend Python | Frontend estático | Todo | Backend Python |
| Plan gratuito | ✅ Sí | ✅ Sí | ✅ Limitado | ✅ $5/mes |
| PostgreSQL incluido | ✅ Gratis | ❌ No | ❌ No | ✅ Gratis |
| Se duerme (free) | ✅ Sí (15min) | N/A | ✅ Sí | ✅ Sí |
| Ideal para | Producción ligera | Frontend | Demo rápido | Prototipos |

---

## COMBINACIÓN RECOMENDADA (gratuita)

```
GitHub ──────────────────────┬──────────────────────────
                             │
                    ┌────────▼────────┐        ┌─────────────────┐
                    │    RENDER       │        │    NETLIFY      │
                    │  FastAPI        │◄───────│  index.html     │
                    │  + PostgreSQL   │  fetch │  styles.css     │
                    │                 │        │  app.js         │
                    └────────┬────────┘        └─────────────────┘
                             │ usa
              ┌──────────────┼──────────────┐
              │              │              │
         ┌────▼───┐   ┌──────▼──┐   ┌──────▼──┐
         │ AWS     │   │ Google  │   │Pinecone │
         │Bedrock  │   │Vertex AI│   │         │
         │   +S3   │   │         │   │         │
         └─────────┘   └─────────┘   └─────────┘
```

---

## CHECKLIST DE DESPLIEGUE

```
PREPARACIÓN
[ ] Código subido a GitHub (sin .env, sin credentials/)
[ ] requirements.txt en la raíz del proyecto (✅ ya creado)
[ ] Procfile en la raíz (✅ ya creado)
[ ] .python-version en la raíz (✅ ya creado)

BACKEND (Render)
[ ] Base de datos PostgreSQL creada en Render
[ ] Web Service creado y conectado al repo de GitHub
[ ] Todas las variables de entorno configuradas
[ ] CORS_ORIGINS incluye la URL de Netlify
[ ] Primera migración ejecutada (tablas creadas)
[ ] /health responde OK: https://tu-app.onrender.com/health

FRONTEND (Netlify)
[ ] window.API_BASE actualizado en index.html con la URL de Render
[ ] Carpeta frontend/ subida a Netlify (drag & drop)
[ ] La UI muestra "API Online" en la esquina inferior izquierda
```

---

## ARCHIVOS NUEVOS CREADOS PARA EL DESPLIEGUE

| Archivo | Propósito |
|---------|-----------|
| `Procfile` | Comando de inicio para Render/Railway/Heroku |
| `requirements.txt` | Dependencias para plataformas que no leen pyproject.toml |
| `.python-version` | Versión de Python (3.11.9) |
