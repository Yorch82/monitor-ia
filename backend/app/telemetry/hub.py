"""Hub WebSocket: broadcast del frame a todos los clientes conectados."""

from __future__ import annotations

import logging

from fastapi import WebSocket

log = logging.getLogger(__name__)


class TelemetryHub:
    """Gestiona las conexiones WS activas y difunde el último snapshot JSON."""

    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._latest: str | None = None

    @property
    def client_count(self) -> int:
        return len(self._clients)

    async def register(self, ws: WebSocket) -> None:
        self._clients.add(ws)
        if self._latest is not None:
            # Al (re)conectarse, el cliente recibe el último frame conocido al instante.
            try:
                await ws.send_text(self._latest)
            except Exception:  # noqa: BLE001
                self._clients.discard(ws)

    def unregister(self, ws: WebSocket) -> None:
        self._clients.discard(ws)

    async def broadcast(self, text: str) -> None:
        """Envía el frame actual a todos; los que fallen se descartan silenciosamente."""
        self._latest = text
        if not self._clients:
            return
        stale: list[WebSocket] = []
        for ws in self._clients:
            try:
                await ws.send_text(text)
            except Exception:  # noqa: BLE001 — cliente cerrado/limpiándose
                stale.append(ws)
        for ws in stale:
            self._clients.discard(ws)
