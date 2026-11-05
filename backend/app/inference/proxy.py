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




@router.post("/v1/chat/completions")
@router.post("/v1/completions")
async def forward_completion(request: Request) -> Any:
    """Reenvía la petición al servidor de inferencia y captura el ``usage``."""
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

    target = f"{settings.inference_base_url.rstrip('/')}{request.url.path[len('/proxy'):]}"
    http: httpx.AsyncClient = state.http_client
    started = time.perf_counter()

    try:
        if body and body.get("stream"):
            return await _forward_streaming(
                http, target, headers, body_bytes, body, state, settings.token_source, started
            )
        return await _forward_json(http, target, headers, body_bytes, body, state, settings.token_source, started)
    except httpx.HTTPError as exc:
        log.warning("Proxy: error conectando con %s: %s", target, exc)
        return JSONResponse(
            status_code=502,
            content={"error": {"message": f"No se pudo conectar con el servidor de inferencia: {exc}"}},
        )


async def _forward_json(
    http: httpx.AsyncClient,
    target: str,
    headers: dict[str, str],
    body_bytes: bytes,
    body: dict[str, Any] | None,
    state: Any,
    token_source: str,
    started: float,
) -> JSONResponse:
    """Caso simple: respuesta JSON completa."""
    resp = await http.post(
        target, content=body_bytes, headers=headers,
        timeout=httpx.Timeout(READ_TIMEOUT_S, connect=CONNECT_TIMEOUT_S),
    )
    usage = _usage_of(resp) if resp.status_code == 200 and resp.headers.get("content-type", "").startswith("application/json") else None
    if usage:
        _record_usage(state, body, usage, started, count_tokens=_should_count(token_source, state))
    return JSONResponse(status_code=resp.status_code, content=_safe_json(resp))


async def _forward_streaming(
    http: httpx.AsyncClient,
    target: str,
    headers: dict[str, str],
    body_bytes: bytes,
    body: dict[str, Any] | None,
    state: Any,
    token_source: str,
    started: float,
) -> StreamingResponse:
    """Streaming: relanza los bytes y escanea el buffer buscando el ``usage`` final."""
    req = http.build_request(
        "POST", target, content=body_bytes, headers=headers,
        timeout=httpx.Timeout(READ_TIMEOUT_S, connect=CONNECT_TIMEOUT_S),
    )
    resp = await http.send(req, stream=True)
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
        return None
    data = usage if isinstance(usage, dict) else {}
    input_tokens = (
        data.get("prompt_tokens")
        or data.get("prompt_eval_count")  # Ollama native
        or data.get("input_tokens")
        or 0
    )
    output_tokens = (
        data.get("completion_tokens")
        or data.get("eval_count")  # Ollama native
        or data.get("output_tokens")
        or 0
    )
    try:
        return {"input": max(0, int(input_tokens)), "output": max(0, int(output_tokens))}
    except (TypeError, ValueError, json.JSONDecodeError):
        return None


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
