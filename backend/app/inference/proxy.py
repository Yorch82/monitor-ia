"""Proxy OpenAI-compatible con captura de tokens.

El cliente de IA apunta a ``http://<backend>/proxy/v1/chat/completions`` (en vez de a
Ollama/vLLM/llama.cpp directamente). El backend reenvía la petición al servidor real
(``inference_base_url``) y registra el ``usage`` de la respuesta para métricas de
tokens por petición y ocupación de contexto.

- No-streaming: parsea el JSON y lee ``usage`` directamente.
- Streaming: reenvía los chunks tal cual mientras los acumula en un buffer; al
  terminar, extrae el último objeto con ``usage`` (compatible con ``stream_options:
  include_usage`` y con engines que incluyen usage en el último chunk).
- Si el contador Prometheus es la fuente autoritativa, no se duplican los tokens en
  el acumulador (``count_tokens=False``), pero sí se registran contexto/last-request.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, AsyncIterator

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from app.core.models import RequestUsage
from app.core.tokens import TokenAggregator

log = logging.getLogger(__name__)

router = APIRouter(prefix="/proxy", tags=["proxy"])

CONNECT_TIMEOUT_S = 5.0
READ_TIMEOUT_S = 600.0  # generaciones largas con streaming

_USAGE_KEY = "usage"

# Endpoints de generación cuya respuesta contiene ``usage`` (chat
# completions clásica + Responses API de OpenAI que usa Open WebUI moderno).
_GEN_PATHS = {"chat/completions", "completions", "responses"}




@router.api_route("/v1/{path:path}", methods=["GET", "POST"])
async def forward_v1(request: Request, path: str) -> Any:
    """Pasarela OpenAI-compatible completa.

    - ``GET`` (p. ej. ``/v1/models``): reenvía la petición tal cual — Open WebUI y
      similares validan la conexión listando modelos.
    - ``POST /v1/chat/completions`` y ``/v1/completions``: además captura el ``usage``.
    - Resto de ``POST``: passthrough puro.
    """
    state = request.app.state
    settings = state.settings_manager.get()
    if settings.simulation_mode:
        return JSONResponse(
            status_code=503,
            content={"error": {"message": "Monitor IA está en modo simulación: no hay servidor de inferencia real. Desactívalo en Ajustes."}},
        )

    body_bytes = await request.body()
    body: dict[str, Any] | None = None
    try:
        body = json.loads(body_bytes or b"{}")
    except json.JSONDecodeError:
        body = {}

    headers: dict[str, str] = {"Content-Type": "application/json"}
    api_key = settings.inference_api_key
    client_auth = request.headers.get("authorization")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    elif client_auth:  # pass-through de la auth del cliente si el backend no tiene key
        headers["Authorization"] = client_auth

    # Evita duplicar el sufijo /v1 si el base ya lo incluye
    # (http://host:11434/v1 + /v1/models → http://host:11434/v1/models).
    base_clean = settings.inference_base_url.rstrip("/")
    sub_path = request.url.path[len("/proxy"):]
    if base_clean.endswith("/v1") and sub_path.startswith("/v1"):
        target = base_clean[:-3] + sub_path
    else:
        target = base_clean + sub_path
    http: httpx.AsyncClient = state.http_client
    started = time.perf_counter()

    # Ayuda a capturar usage en streaming: si el cliente no pidió usage, se inyecta
    # stream_options.include_usage (Ollama/vLLM/llama.cpp modernos lo soportan).
    # Si el engine rechaza el campo extra, se reintenta con el body original.
    injected = False
    if body and body.get("stream") and path in ("chat/completions", "completions") \
            and body.get("stream_options") is None:
        body = dict(body); body["stream_options"] = {"include_usage": True}
        body_bytes = json.dumps(body, ensure_ascii=False).encode()
        injected = True

    try:
        if request.method == "GET":
            # Listado de modelos y similares: passthrough (con query incluido).
            get_url = f"{target}?{request.url.query}" if request.url.query else target
            resp = await http.get(
                get_url, headers=headers,
                timeout=httpx.Timeout(30.0, connect=CONNECT_TIMEOUT_S),
            )
            return JSONResponse(status_code=resp.status_code, content=_safe_json(resp))
        if path not in _GEN_PATHS:
            # POST no-generativo (embeddings, files…): passthrough puro.
            resp = await http.post(
                target, content=body_bytes, headers=headers,
                timeout=httpx.Timeout(READ_TIMEOUT_S, connect=CONNECT_TIMEOUT_S),
            )
            if resp.status_code == 200:
                usage = _usage_of(resp)
                if usage:
                    _record_usage(state, body, usage, started, count_tokens=_should_count(settings.token_source, state))
            return JSONResponse(status_code=resp.status_code, content=_safe_json(resp))
        if body and body.get("stream"):
            resp_stream = await _open_stream(http, target, headers, body_bytes)
            if injected and resp_stream.status_code >= 400:
                # Fallback: engine no soporta stream_options → reintenta con el body original.
                await resp_stream.aclose()
                original = {k: v for k, v in (body or {}).items() if k != "stream_options"}
                resp_stream = await _open_stream(http, target, headers, json.dumps(original, ensure_ascii=False).encode())
            return await _relay_stream(resp_stream, body, state, settings.token_source, started)
        resp = await http.post(
            target, content=body_bytes, headers=headers,
            timeout=httpx.Timeout(READ_TIMEOUT_S, connect=CONNECT_TIMEOUT_S),
        )
        usage = _usage_of(resp) if resp.status_code == 200 and resp.headers.get("content-type", "").startswith("application/json") else None
        if usage:
            _record_usage(state, body, usage, started, count_tokens=_should_count(settings.token_source, state))
        return JSONResponse(status_code=resp.status_code, content=_safe_json(resp))
    except httpx.HTTPError as exc:
        log.warning("Proxy: error conectando con %s: %s", target, exc)
        return JSONResponse(
            status_code=502,
            content={"error": {"message": f"No se pudo conectar con el servidor de inferencia: {exc}"}},
        )


async def _open_stream(http, target, headers, body_bytes):
    req = http.build_request(
        "POST", target, content=body_bytes, headers=headers,
        timeout=httpx.Timeout(READ_TIMEOUT_S, connect=CONNECT_TIMEOUT_S),
    )
    return await http.send(req, stream=True)


async def _relay_stream(resp: httpx.Response, body, state, token_source, started) -> StreamingResponse:
    """Streaming: reenvía los bytes tal cual y escanea el buffer buscando el usage final."""
    buffer = bytearray()

    async def gen() -> AsyncIterator[bytes]:
        try:
            async for chunk in resp.aiter_bytes():
                buffer.extend(chunk)
                yield chunk
        finally:
            await resp.aclose()
            usage = _usage_from_stream(bytes(buffer))
            if usage:
                _record_usage(state, body, usage, started, count_tokens=_should_count(token_source, state))

    media_type = resp.headers.get("content-type", "text/event-stream")
    return StreamingResponse(gen(), status_code=resp.status_code, media_type=media_type)


# ── extracción del usage ─────────────────────────────────────────────────────


def _usage_of(resp: httpx.Response) -> dict[str, Any] | None:
    try:
        data = resp.json()
    except (json.JSONDecodeError, ValueError):
        return None
    return _usage_tokens(data if isinstance(data, dict) else {})


def _usage_from_stream(text: bytes) -> dict[str, Any] | None:
    """Último objeto JSON con ``usage`` dentro de un stream SSE."""
    usage = None
    for line in text.split(b"\n"):
        line = line.strip()
        if not line.startswith(b"data:"):
            continue
        payload = line[5:].strip()
        if not payload or payload == b"[DONE]":
            continue
        try:
            obj = json.loads(payload)
        except json.JSONDecodeError:
            continue
        found = _usage_tokens(obj)
        if found:
            usage = found
    return usage


def _usage_tokens(obj: dict[str, Any]) -> dict[str, Any] | None:
    """Normaliza el bloque usage a {input, output}. Soporta variantes de engines."""
    usage = obj.get(_USAGE_KEY)
    if not isinstance(usage, dict):
        # Responses API: usage anidada en {"type":"response.completed","response":{usage}}.
        inner = obj.get("response")
        usage = inner.get(_USAGE_KEY) if isinstance(inner, dict) else None
    if not isinstance(usage, dict):
        return None
    data = usage if isinstance(usage, dict) else {}
    input_tokens = (
        data.get("prompt_tokens")
        or data.get("prompt_eval_count")  # Ollama native
        or data.get("input_tokens")       # Responses API
        or 0
    )
    output_tokens = (
        data.get("completion_tokens")
        or data.get("eval_count")         # Ollama native
        or data.get("output_tokens")      # Responses API
        or 0
    )
    try:
        out_i = max(0, int(input_tokens)); out_o = max(0, int(output_tokens))
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    if out_i == 0 and out_o == 0:
        return None
    return {"input": out_i, "output": out_o}


def _should_count(token_source: str, state: Any) -> bool:
    """¿Deben sumarse estos tokens al acumulador del proxy?

    - ``token_source='proxy'``: siempre (es la fuente elegida).
    - auto: solo si las métricas Prometheus no están activas (evita doble conteo).
    - ``prometheus``/``none``: nunca.
    El último-request/contexto se registran igualmente en todos los casos.
    """
    if token_source == "proxy":
        return True
    if token_source == "auto":
        return not getattr(state.inference_monitor, "prometheus_active", False)
    return False


def _record_usage(state: Any, body: dict[str, Any] | None, usage: dict[str, Any], started: float, count_tokens: bool) -> None:
    agg: TokenAggregator = state.proxy_aggregator
    usage_seen = RequestUsage(
        ts=time.time(),
        input_tokens=usage["input"],
        output_tokens=usage["output"],
        duration_s=max(0.001, time.perf_counter() - started),
        model=(body or {}).get("model"),
    )
    agg.record_request(usage_seen, count_tokens=count_tokens)


def _safe_json(resp: httpx.Response) -> Any:
    try:
        return resp.json()
    except (json.JSONDecodeError, ValueError):
        return {"error": {"message": "El servidor de inferencia devolvió una respuesta no JSON"}}
