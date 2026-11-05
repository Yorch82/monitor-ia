"""API REST + WebSocket.

- ``GET /api/health``            : estado del proceso.
- ``GET /api/telemetry``        : último frame (para el arranque del dashboard).
- ``WS /ws/telemetry``          : stream en tiempo real (casi cada tick).
- ``GET /api/history?range=…``  : puntos agregados 1m/15m/1h/24h para las gráficas.
- ``GET /api/export.csv?range`` : descarga del histórico crudo en CSV.
- ``GET/PUT /api/settings``     : settings runtime (persistidos en SQLite).
- ``POST /api/settings/reset``  : restaura defaults de .env.
- ``POST /api/session/reset``   : reinicia tokens/energía de la sesión.
El proxy OpenAI-compatible se define en ``app.inference.proxy``.
"""

from __future__ import annotations

import csv
import io
import logging
import time
from typing import Any

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, StreamingResponse

from app.core.settings import RuntimeSettings
from app.storage.database import RANGES

log = logging.getLogger(__name__)

router = APIRouter()


# ── estado básico ─────────────────────────────────────────────────────────────


@router.get("/api/health")
async def health(request: Request) -> dict[str, Any]:
    state = request.app.state
    s: RuntimeSettings = state.settings_manager.get()
    return {
        "status": "ok",
        "mode": "simulation" if s.simulation_mode else "live",
        "uptime_s": round(state.telemetry_sampler.uptime_s(), 1),
        "interval_ms": int(s.refresh_interval_s * 1000),
        "ws_clients": state.telemetry_hub.client_count,
    }


@router.get("/api/telemetry")
async def telemetry(request: Request) -> dict[str, Any]:
    """Último frame; si aún no hay muestra, ``snapshot: null`` (la UI muestra estado inicial)."""
    frame = request.app.state.telemetry_sampler.latest()
    return {"snapshot": frame.to_dict(), "uptime_s": round(request.app.state.telemetry_sampler.uptime_s(), 1)}


@router.websocket("/ws/telemetry")
async def telemetry_ws(ws: WebSocket) -> None:
    hub = ws.app.state.telemetry_hub
    await ws.accept()
    await hub.register(ws)
    try:
        while True:
            # El cliente puede mandar "ping" (keepalives falsos); se ignoran.
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001 — shutdown del servidor también sale por aquí
        pass
    finally:
        hub.unregister(ws)


# ── histórico / export ────────────────────────────────────────────────────────


@router.get("/api/history")
async def history(request: Request, range: str = "15m") -> Any:
    if range not in RANGES:
        return JSONResponse(status_code=400, content={"detail": "rango inválido"})
    return request.app.state.history_store.history_points(range)


@router.get("/api/export.csv")
async def export_csv(request: Request, range: str = "24h") -> StreamingResponse:
    """Historico crudo en CSV (UTF-8 con BOM para Excel)."""
    if range not in RANGES:
        return JSONResponse(status_code=400, content={"detail": "rango inválido"})

    buf_header = io.StringIO()
    writer = csv.writer(buf_header)
    writer.writerow(CSV_COLUMNS)
    header_line = buf_header.getvalue()

    def gen():
        yield header_line
        for row in request.app.state.history_store.csv_rows(range):
            out = io.StringIO()
            writer = csv.writer(out)
            writer.writerow(row)
            yield out.getvalue()

    stamp = time.strftime("%Y%m%d-%H%M%S")
    return StreamingResponse(
        gen(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="monitor-ia-{range}-{stamp}.csv"',
        },
    )


CSV_COLUMNS = [
    "timestamp_utc", "mode", "tokens_input_total", "tokens_output_total", "tokens_total",
    "tokens_per_s_ma60", "context_pct", "gpu_avg_pct", "gpu_temp_max_c", "vram_avg_pct",
    "power_w", "energy_session_wh", "ram_pct", "cpu_pct", "cost_per_hour_eur",
    "session_cost_eur",
]


# ── settings ──────────────────────────────────────────────────────────────────


@router.get("/api/settings")
async def get_settings(request: Request) -> dict[str, Any]:
    return request.app.state.settings_manager.get().to_public_dict()


@router.put("/api/settings")
async def put_settings(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    """Update parcial de settings; se valida/acota en ``RuntimeSettings.apply_update``."""
    state = request.app.state
    mgr = state.settings_manager
    current = mgr.get()
    try:
        new_settings = current.apply_update(payload)
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(status_code=400, content={"detail": f"Configuración inválida: {exc}"})
    mgr.update(new_settings)
    state.history_store.save_runtime_settings(new_settings.to_persisted_dict())
    state.telemetry_sampler.reconfigure(new_settings)
    return new_settings.to_public_dict()


@router.post("/api/settings/reset")
async def reset_settings(request: Request) -> dict[str, Any]:
    """Borra lo persistido y vuelve a los defaults del .env."""
    state = request.app.state
    from app.config import get_config

    base = RuntimeSettings.from_config(get_config(), None)
    state.settings_manager.update(base)
    state.history_store.delete_runtime_settings()
    state.telemetry_sampler.reconfigure(base)
    return base.to_public_dict()


@router.post("/api/session/reset")
async def reset_session(request: Request) -> dict[str, Any]:
    """Reinicia tokens/energía/costes de la sesión (no borra el histórico)."""
    request.app.state.telemetry_sampler.reset_session()
    return {"status": "ok"}
