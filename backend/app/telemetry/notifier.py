"""Notificador de alertas por webhook (sin bloquear, errores silenciosos)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

log = logging.getLogger(__name__)


async def send_webhook(client: httpx.AsyncClient, url: str, alert: dict[str, Any]) -> None:
    """Envía el payload de la alerta (fire-and-forget). Nunca lanza ni rompe el tick."""
    if not url:
        return

    async def _post() -> None:
        try:
            await client.post(
                url,
                json={"app": "monitor-ia", "type": "alert", "alert": alert},
                timeout=httpx.Timeout(5.0),
            )
        except Exception as exc:  # noqa: BLE001 — webhook es opcional
            log.debug("Webhook falló (%s): %s", url, exc)

    asyncio.create_task(_post())
