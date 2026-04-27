#!/usr/bin/env python3
"""
FASE 8 — End-to-End Demo Script
Multi-Agent AI Platform

Flujo completo:
  1. Crear agente
  2. Subir documento (PDF de texto plano simulado)
  3. Hacer consulta (chat con orquestador)
  4. Respuesta con fuentes

Usage:
    python e2e_demo.py

Requires:
    pip install httpx rich     (solo para este script)
    Backend corriendo en:  http://localhost:8000
"""
from __future__ import annotations

import io
import sys
import time

try:
    import httpx
    from rich import print as rprint
    from rich.console import Console
    from rich.panel import Panel
    from rich.syntax import Syntax
    from rich.table import Table
except ImportError:
    print("ERROR: Instala las dependencias del script:")
    print("  pip install httpx rich")
    sys.exit(1)

# ── Config ────────────────────────────────────────────────────────────────────
BASE_URL   = "http://localhost:8000/api/v1"
USER_ID    = "demo-user-id"
TENANT_ID  = 1

console = Console()

DEMO_DOCUMENT_TEXT = """\
MANUAL TÉCNICO — IMPRESORAS HP LASERJET PRO

1. INTRODUCCIÓN
La impresora HP LaserJet Pro M404dn es una impresora láser monocromática
diseñada para entornos de oficina de pequeño y mediano tamaño. Ofrece
velocidades de hasta 40 páginas por minuto (ppm) y resolución de 1200 x 1200 dpi.

2. ESPECIFICACIONES TÉCNICAS
- Velocidad de impresión: 40 ppm (carta), 38 ppm (A4)
- Resolución: 1200 x 1200 dpi efectivo
- Ciclo de trabajo mensual: hasta 80,000 páginas
- Capacidad de papel estándar: 350 hojas (bandejas 1 y 2)
- Conectividad: Ethernet Gigabit, Wi-Fi 802.11 b/g/n, USB 2.0
- Memoria RAM: 256 MB
- Procesador: 1.2 GHz dual core
- Dimensiones: 38.4 x 39 x 22.3 cm, Peso: 8.4 kg

3. CONFIGURACIÓN INICIAL
3.1 Conexión de red por cable (Ethernet)
    a) Conecte el cable Ethernet al puerto RJ-45 en la parte trasera de la impresora.
    b) Conecte el otro extremo al switch o router de red.
    c) La impresora asignará automáticamente una dirección IP por DHCP.
    d) Para ver la IP asignada: imprima la página de configuración de red
       desde el panel de control: Menú → Configuración → Informes → Página de configuración.

3.2 Instalación de controlador en Windows 10/11
    a) Descargue el controlador desde: support.hp.com/drivers
    b) Ejecute el instalador HP LaserJet Pro M404dn_Full_Solution.exe
    c) Seleccione "Conexión de red" cuando se le solicite el tipo de conexión.
    d) El instalador detectará automáticamente la impresora en la red.
    e) Complete el asistente de instalación y reinicie si se solicita.

4. RESOLUCIÓN DE PROBLEMAS COMUNES
4.1 Atascos de papel
    Causa: Papel húmedo, mal alimentado, o de gramaje incorrecto.
    Solución:
    - Abra la cubierta superior y retire cuidadosamente el papel atascado.
    - Verifique que el papel esté dentro de la especificación: 60-200 g/m².
    - No utilice papel arrugado, húmedo o con grapas.

4.2 Calidad de impresión deficiente (rayas o manchas)
    Causa: Cartucho de tóner bajo o defectuoso.
    Solución:
    - Saque el cartucho de tóner y agítelo suavemente de lado a lado.
    - Esto redistribuye el tóner y puede mejorar la calidad temporalmente.
    - Reemplace el cartucho si el problema persiste (HP CF258A o CF258X).

4.3 La impresora no aparece en la red
    Solución:
    - Verifique que el cable Ethernet esté correctamente conectado.
    - Imprima la página de configuración de red para confirmar la IP.
    - Asegúrese de que el firewall del PC no bloquee el puerto 9100 (impresión directa).
    - Reinicie la impresora y el router.

5. CONSUMIBLES Y MANTENIMIENTO
- Cartucho de tóner: HP 58A (CF258A) — rendimiento ~3,000 pág.
- Cartucho de tóner: HP 58X (CF258X) — rendimiento ~10,000 pág. (alta capacidad)
- Unidad de imagen: HP CF232A — reemplazar cada ~23,000 páginas.
- Limpieza del rodillo de alimentación: cada 6 meses o 50,000 páginas.

6. GARANTÍA
La impresora HP LaserJet Pro M404dn incluye garantía limitada de 1 año
de piezas y mano de obra. Para soporte técnico: 1-800-474-6836
o visite support.hp.com.
"""


def header(text: str) -> None:
    console.rule(f"[bold cyan]{text}[/bold cyan]")
    console.print()


def success(text: str) -> None:
    console.print(f"  [bold green]✓[/bold green] {text}")


def info(text: str) -> None:
    console.print(f"  [dim cyan]→[/dim cyan] {text}")


def error(text: str) -> None:
    console.print(f"  [bold red]✗[/bold red] {text}")


# ── Steps ─────────────────────────────────────────────────────────────────────

def step1_create_agent(client: httpx.Client) -> dict:
    """Crea un agente especializado en impresoras HP."""
    header("PASO 1 — Crear Agente")

    payload = {
        "name": "HP LaserJet Expert",
        "topic": "Impresoras HP LaserJet",
        "description": "Agente especializado en soporte técnico de impresoras HP LaserJet Pro.",
        "system_prompt": (
            "Eres un experto técnico en impresoras HP LaserJet. "
            "Responde únicamente basándote en la documentación técnica oficial de HP. "
            "Si la respuesta no está en el contexto proporcionado, indica que no tienes "
            "suficiente información en tu base de conocimiento. "
            "Siempre proporciona pasos claros y numerados cuando expliques procedimientos."
        ),
        "llm_model": "anthropic.claude-3-5-sonnet-20241022-v2:0",
        "llm_temperature": 0.1,
        "llm_max_tokens": 2048,
    }

    info(f"POST {BASE_URL}/agents")
    info(f"Nombre: {payload['name']}")
    info(f"Tema: {payload['topic']}")

    resp = client.post(
        f"{BASE_URL}/agents",
        json=payload,
        params={"user_id": USER_ID, "tenant_id": TENANT_ID},
        timeout=30,
    )
    resp.raise_for_status()
    agent = resp.json()

    console.print()
    t = Table(show_header=False, border_style="dim")
    t.add_column("Campo", style="dim cyan", width=22)
    t.add_column("Valor", style="white")
    t.add_row("ID", agent["id"])
    t.add_row("Nombre", agent["name"])
    t.add_row("Topic", agent["topic"])
    t.add_row("Namespace Pinecone", agent["pinecone_namespace"])
    t.add_row("Modelo LLM", agent["llm_model"])
    t.add_row("Modelo Embedding", agent["embedding_model"])
    t.add_row("Estado KB", agent.get("knowledge_base", {}).get("status", "—") if agent.get("knowledge_base") else "—")
    console.print(t)
    console.print()

    success(f"Agente creado con ID: [bold]{agent['id']}[/bold]")
    return agent


def step2_upload_document(client: httpx.Client, agent_id: str) -> dict:
    """Sube un documento TXT al agente."""
    header("PASO 2 — Subir Documento")

    doc_bytes = DEMO_DOCUMENT_TEXT.encode("utf-8")
    filename = "hp_laserjet_pro_manual.txt"

    info(f"POST {BASE_URL}/agents/{agent_id}/documents")
    info(f"Archivo: {filename} ({len(doc_bytes):,} bytes)")
    info("Proceso: S3 upload → registro SQL → [background] parse → chunk → embed → Pinecone upsert")
    console.print()

    resp = client.post(
        f"{BASE_URL}/agents/{agent_id}/documents",
        files={"file": (filename, io.BytesIO(doc_bytes), "text/plain")},
        params={"user_id": USER_ID},
        timeout=60,
    )
    resp.raise_for_status()
    result = resp.json()
    doc = result["document"]

    t = Table(show_header=False, border_style="dim")
    t.add_column("Campo", style="dim cyan", width=22)
    t.add_column("Valor", style="white")
    t.add_row("Document ID", doc["id"])
    t.add_row("Nombre", doc["file_name"])
    t.add_row("Estado inicial", doc["status"])
    t.add_row("Procesamiento iniciado", str(result["processing_started"]))
    t.add_row("Storage path", doc.get("storage_path", "—"))
    console.print(t)
    console.print()

    success("Documento subido. Procesamiento iniciado en background.")
    info("Esperando procesamiento: parse → chunk → embed → upsert a Pinecone…")

    # Poll hasta que el documento esté listo (max 90 seg)
    doc_id = doc["id"]
    for attempt in range(18):
        time.sleep(5)
        poll_resp = client.get(
            f"{BASE_URL}/agents/{agent_id}/documents/{doc_id}",
            timeout=15,
        )
        if poll_resp.status_code == 200:
            doc_updated = poll_resp.json()
            status = doc_updated.get("status", "?")
            console.print(f"  [dim]  Intento {attempt+1}: status = [bold]{status}[/bold][/dim]")
            if status == "ready":
                console.print()
                success(
                    f"Documento procesado. "
                    f"Chunks: [bold]{doc_updated.get('total_chunks', '?')}[/bold]"
                )
                return doc_updated
            elif status == "failed":
                error(f"Procesamiento falló: {doc_updated.get('error_message', 'desconocido')}")
                return doc_updated
        else:
            info(f"  Poll {attempt+1}: HTTP {poll_resp.status_code}")

    console.print()
    info("Tiempo de espera agotado. Continuando con la consulta de todos modos.")
    return doc


def step3_chat(client: httpx.Client, agent_id: str | None = None) -> dict:
    """Envía una consulta al orquestador (o directo al agente)."""
    header("PASO 3 — Consulta al Sistema (Chat)")

    question = "¿Cuál es el cartucho de tóner recomendado para alta capacidad y cuántas páginas rinde?"
    mode     = "Orquestador automático" if not agent_id else f"Directo al agente {agent_id[:8]}…"

    info(f"POST {BASE_URL}/chat")
    info(f"Modo: {mode}")
    info(f"Pregunta: \"{question}\"")
    console.print()

    payload = {
        "user_id":   USER_ID,
        "message":   question,
        "tenant_id": TENANT_ID,
    }
    if agent_id:
        payload["agent_id"] = agent_id

    resp = client.post(
        f"{BASE_URL}/chat",
        json=payload,
        timeout=120,
    )
    resp.raise_for_status()
    result = resp.json()
    return result


def step4_display_response(result: dict) -> None:
    """Muestra la respuesta estructurada con fuentes."""
    header("PASO 4 — Respuesta con Fuentes")

    # Agente usado
    agent_used = result.get("agent_used")
    if agent_used:
        console.print(Panel(
            f"[bold cyan]{agent_used['name']}[/bold cyan]\n"
            f"[dim]Topic: {agent_used['topic']}[/dim]",
            title="🤖 Agente Seleccionado",
            border_style="cyan",
            expand=False,
        ))
        console.print()

    if result.get("routing_reason"):
        console.print(f"  [dim]Razón de routing: {result['routing_reason']}[/dim]")
        console.print()

    # Respuesta
    console.print(Panel(
        result.get("answer", "(sin respuesta)"),
        title="💬 Respuesta",
        border_style="green",
    ))
    console.print()

    # Fuentes
    sources = result.get("sources", [])
    if sources:
        t = Table(title=f"📚 Fuentes ({len(sources)})", border_style="dim", show_lines=True)
        t.add_column("Archivo", style="cyan")
        t.add_column("Chunk #", justify="right", style="dim")
        t.add_column("Páginas", justify="right", style="dim")
        t.add_column("Score", justify="right", style="bold green")
        for s in sources:
            pages = (
                f"{s['page_from']}–{s['page_to']}"
                if s.get("page_from") is not None
                else "—"
            )
            t.add_row(
                s["filename"],
                str(s["chunk_index"]),
                pages,
                f"{s['score']:.4f}",
            )
        console.print(t)
        console.print()
        success(f"{len(sources)} fuente(s) recuperada(s) de Pinecone.")
    else:
        console.print("  [dim yellow]⚠ Sin fuentes (el agente respondió sin RAG o no encontró chunks).[/dim yellow]")
        console.print()

    # Tokens
    tokens_in  = result.get("prompt_tokens", 0)
    tokens_out = result.get("completion_tokens", 0)
    info(f"Tokens usados — Prompt: {tokens_in:,}  /  Completion: {tokens_out:,}  /  Total: {tokens_in + tokens_out:,}")
    info(f"Session ID: {result.get('session_id', '—')}")
    info(f"Message ID: {result.get('message_id', '—')}")

    if result.get("error"):
        console.print()
        error(f"Error en la respuesta: {result['error']}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    console.print()
    console.print(Panel.fit(
        "[bold cyan]NeuralFlux — Multi-Agent AI Platform[/bold cyan]\n"
        "[dim]FASE 8: Ejemplo End-to-End completo[/dim]\n\n"
        "  1. Crear agente\n"
        "  2. Subir documento\n"
        "  3. Hacer consulta\n"
        "  4. Respuesta con fuentes",
        border_style="cyan",
    ))
    console.print()

    # Verificar que el backend esté corriendo
    try:
        with httpx.Client(base_url=BASE_URL) as probe:
            r = probe.get("/../../health", timeout=5)
            if r.status_code == 200:
                success(f"Backend online en {BASE_URL}")
            else:
                info(f"Backend responde con HTTP {r.status_code}")
    except Exception:
        error(f"No se puede conectar al backend en {BASE_URL}")
        error("Asegúrate de que el servidor esté corriendo:")
        console.print("  [bold]uvicorn app.main:app --reload --port 8000[/bold]")
        sys.exit(1)

    console.print()

    with httpx.Client(base_url=BASE_URL) as client:
        try:
            # PASO 1: Crear agente
            agent = step1_create_agent(client)
            agent_id = agent["id"]

            # PASO 2: Subir documento
            step2_upload_document(client, agent_id)

            # PASO 3: Chat
            # Probamos primero con el orquestador automático (sin agent_id)
            # El orquestador debe seleccionar nuestro agente basado en la consulta.
            # Si quieres bypass directo: pasar agent_id=agent_id
            result = step3_chat(client, agent_id=None)

            # PASO 4: Mostrar respuesta
            step4_display_response(result)

            console.print()
            console.rule("[bold green] DEMO COMPLETADO [/bold green]")
            console.print()

        except httpx.HTTPStatusError as exc:
            console.print()
            error(f"HTTP {exc.response.status_code}: {exc.response.text[:500]}")
            console.print_exception()
            sys.exit(1)
        except Exception:
            console.print()
            console.print_exception()
            sys.exit(1)


if __name__ == "__main__":
    main()
