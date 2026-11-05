"""Middleware ASGI que captura peticiones sospechosas al backend.

Se implementa como middleware ASGI puro (no ``BaseHTTPMiddleware``) para no
interferir con el streaming SSE del proxy ni con los WebSockets. Solo registra
peticiones a rutas que **no** pertenecen a la API del dashboard (escaneos,
endpoints inexistentes, etc.). Las peticiones normales del dashboard se ignoran
para no inundar el histórico de seguridad.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Callable, Awaitable

from app.security.parsers import SecurityEventDraft, build_http_event

Send = Callable[[dict[str, Any]], Awaitable[None]]

_IGNORED_PREFIXES = (
    "/api/",          # API propia del dashboard (incluye /api/security)
    "/proxy/",        # generación de IA: ya se monitoriza en Tokens
    "/ws/",           # WebSocket
    "/docs",
    "/openapi.json",
    "/redoc",
    "/favicon.ico",
)


class SecurityRecorder:
    """Cola en memoria entre middleware y servicio (drop silencioso si se llena)."""

    def __init__(self, enabled: bool = True, maxsize: int = 500) -> None:
        self.enabled = enabled
        self._queue: asyncio.Queue[SecurityEventDraft] = asyncio.Queue(maxsize=maxsize)

    def put(self, event: SecurityEventDraft) -> None:
        if not self.enabled:
            return
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            pass

    def drain(self) -> list[SecurityEventDraft]:
        out: list[SecurityEventDraft] = []
        while True:
            try:
                out.append(self._queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        return out


class SecurityHTTPMiddleware:
    """Middleware ASGI con contador de estado para clasificar escaneos web."""

    def __init__(self, app: Any, recorder: SecurityRecorder) -> None:
        self.app = app
        self.recorder = recorder

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Send) -> None:
        if scope.get("type") != "http" or not self.recorder.enabled:
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if any(path == p or path.startswith(p) for p in _IGNORED_PREFIXES):
            await self.app(scope, receive, send)
            return

        status_holder = {"status": 0}

        async def send_wrapper(message: dict[str, Any]) -> None:
            if message.get("type") == "http.response.start":
                status_holder["status"] = int(message.get("status", 0))
            await send(message)

        await self.app(scope, receive, send_wrapper)

        headers = {k.lower(): v for k, v in (scope.get("headers") or [])}
        user_agent = headers.get(b"user-agent", b"").decode("utf-8", "replace")
        ip = _client_ip(scope, headers)
        method = scope.get("method", "GET")
        event = build_http_event(
            ts=time.time(),
            ip=ip,
            path=path,
            method=method,
            user_agent=user_agent,
            status=status_holder["status"],
        )
        self.recorder.put(event)


def _client_ip(scope: dict[str, Any], headers: dict[bytes, bytes]) -> str:
    """IP real del cliente (nginx inyecta X-Real-IP / X-Forwarded-For)."""
    for header in (b"x-real-ip", b"x-forwarded-for"):
        value = headers.get(header)
        if value:
            return value.decode("utf-8", "replace").split(",")[0].strip()
    client = scope.get("client")
    return client[0] if client else "desconocida"
