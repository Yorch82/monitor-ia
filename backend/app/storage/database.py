"""Almacén SQLite: histórico de muestras, settings runtime, export CSV y agregación.

- Tabla ``samples``: una fila por tick con las métricas planas que alimentan las
  gráficas/CSV, más el payload JSON completo del frame.
- Tabla ``settings``: JSON del ``RuntimeSettings`` (clave 'runtime') con prioridad
  sobre .env al arrancar.
- ``history_points``: agregación por buckets SQL (AVG) para servir 1m/15m/1h/24h
  con un nº de puntos acotado independiente del intervalo de muestreo.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

log = logging.getLogger(__name__)

# (segundos de rango, segundos por bucket): nº de puntos resultante acotado (~60-360).
RANGES: dict[str, tuple[float, float]] = {
    "1m": (60, 1),
    "15m": (900, 4),
    "1h": (3600, 12),
    "24h": (86400, 60),
}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    input_total INTEGER,
    output_total INTEGER,
    moving_avg_tps REAL,
    context_pct REAL,
    gpu_pct REAL,
    gpu_temp_c REAL,
    vram_pct REAL,
    power_w REAL,
    energy_wh REAL,
    ram_pct REAL,
    cpu_pct REAL,
    cost_per_hour REAL,
    payload TEXT
);
CREATE INDEX IF NOT EXISTS idx_samples_ts ON samples(ts);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


class HistoryStore:
    """Acceso a SQLite. Thread-safe (lock) aunque todo el uso es desde el event loop."""

    def __init__(self, db_path: Path) -> None:
        self._path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    # ── samples ──────────────────────────────────────────────────────────────

    def insert_sample(
        self,
        ts: float,
        payload: dict[str, Any],
        input_total: int,
        output_total: int,
        moving_avg_tps: float | None,
        context_pct: float | None,
        gpu_pct: float | None,
        gpu_temp_c: float | None,
        vram_pct: float | None,
        power_w: float | None,
        energy_wh: float,
        ram_pct: float | None,
        cpu_pct: float | None,
        cost_per_hour: float | None,
    ) -> None:
        """Inserta la fila del tick (payload completo en JSON para CSV/futuras vistas)."""
        with self._lock:
            self._conn.execute(
                """INSERT INTO samples (ts, input_total, output_total, moving_avg_tps,
                   context_pct, gpu_pct, gpu_temp_c, vram_pct, power_w, energy_wh,
                   ram_pct, cpu_pct, cost_per_hour, payload)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (ts, input_total, output_total, moving_avg_tps, context_pct, gpu_pct,
                 gpu_temp_c, vram_pct, power_w, energy_wh, ram_pct, cpu_pct,
                 cost_per_hour, json.dumps(payload, ensure_ascii=False)),
            )
            self._conn.commit()

    def energy_since(self, ts_from: float) -> float:
        """Suma de energía Wh registrada desde una marca temporal (coste diario)."""
        with self._lock:
            row = self._conn.execute(
                "SELECT COALESCE(SUM(energy_wh), 0) FROM samples WHERE ts >= ?", (ts_from,)
            ).fetchone()
        return float(row[0] if row else 0.0)

    def prune(self, retention_hours: int) -> int:
        """Borra muestras más antiguas que la retención configurada."""
        cutoff = time.time() - retention_hours * 3600
        with self._lock:
            cur = self._conn.execute("DELETE FROM samples WHERE ts < ?", (cutoff,))
            self._conn.commit()
        return cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0

    # ── gráficas: agregación por buckets ────────────────────────────────────

    def history_points(self, range_key: str) -> dict[str, Any]:
        """Puntos agregados para las gráficas (misma forma que el punto vivo del WS)."""
        if range_key not in RANGES:
            raise ValueError(f"Rango inválido: {range_key}")
        span, bucket = RANGES[range_key]
        now = time.time()
        ts_from = now - span
        with self._lock:
            rows = self._conn.execute(
                f"""
                SELECT
                    (CAST(ts / {bucket} AS INTEGER) * {bucket}) AS bts,
                    AVG(moving_avg_tps),
                    MAX(input_total), MIN(input_total),
                    MAX(output_total), MIN(output_total),
                    AVG(context_pct),
                    AVG(gpu_pct), AVG(gpu_temp_c), AVG(vram_pct),
                    AVG(power_w),
                    AVG(ram_pct), AVG(cpu_pct),
                    AVG(cost_per_hour)
                FROM samples
                WHERE ts >= ?
                GROUP BY bts
                ORDER BY bts
                """,
                (ts_from,),
            ).fetchall()

        points: list[dict[str, Any]] = []
        for row in rows:
            bts = int(row[0])
            max_in, min_in = row[2] or 0, row[3] or 0
            max_out, min_out = row[4] or 0, row[5] or 0
            points.append(
                {
                    "t": bts * 1000,  # ms epoch para el eje temporal del chart
                    "moving_avg_per_s": _r(row[1]),
                    "input_per_s": _r(max(0.0, (max_in - min_in) / bucket)),
                    "output_per_s": _r(max(0.0, (max_out - min_out) / bucket)),
                    "input_total": int(max_in or 0),
                    "output_total": int(max_out or 0),
                    "context_pct": _r(row[6]),
                    "gpu_pct": _r(row[7]),
                    "gpu_temp_c": _r(row[8]),
                    "vram_pct": _r(row[9]),
                    "power_w": _r(row[10]),
                    "ram_pct": _r(row[11]),
                    "cpu_pct": _r(row[12]),
                    "cost_per_hour": _r(row[13]),
                }
            )
        return {"range": range_key, "bucket_seconds": bucket, "points": points}

    def csv_rows(self, range_key: str) -> Iterator[list[str]]:
        """Iterador de filas crudas para el export CSV (sin cargar todo en RAM)."""
        if range_key not in RANGES:
            raise ValueError(f"Rango inválido: {range_key}")
        span, _ = RANGES[range_key]
        ts_from = time.time() - span
        with self._lock:
            cur = self._conn.execute(
                "SELECT ts, payload FROM samples WHERE ts >= ? ORDER BY ts", (ts_from,)
            )
            while True:
                rows = cur.fetchmany(500)
                if not rows:
                    break
                for ts, payload_json in rows:
                    payload = json.loads(payload_json) if payload_json else {}
                    yield _csv_row(ts, payload)

    # ── settings runtime ────────────────────────────────────────────────────

    def load_runtime_settings(self) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT value FROM settings WHERE key = 'runtime'"
            ).fetchone()
        if not row:
            return None
        try:
            return json.loads(row[0])
        except json.JSONDecodeError:
            log.warning("Settings persistidos corruptos; se usarán los de .env")
            return None

    def save_runtime_settings(self, settings: dict[str, Any]) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO settings (key, value) VALUES ('runtime', ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (json.dumps(settings, ensure_ascii=False),),
            )
            self._conn.commit()

    def delete_runtime_settings(self) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM settings WHERE key = 'runtime'")
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()


def _r(value: Any) -> float | None:
    """Redondeo seguro para columnas numéricas."""
    if value is None:
        return None
    return round(float(value), 3)


def _csv_row(ts: float, payload: dict[str, Any]) -> list[str]:
    tokens = payload.get("tokens") or {}
    context = payload.get("context") or {}
    system = payload.get("system") or {}
    hardware = payload.get("hardware") or {}
    cost = payload.get("cost") or {}
    gpus = payload.get("gpus") or []
    gpu_temps = [g.get("temperature_c") for g in gpus if g.get("temperature_c") is not None]
    return [
        datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(timespec="seconds"),
        hardware.get("mode", ""),
        str(tokens.get("input_tokens", 0)),
        str(tokens.get("output_tokens", 0)),
        str(tokens.get("total_tokens", 0)),
        str(tokens.get("moving_avg_output_per_s", "")),
        str(context.get("percent", "")),
        str(payload.get("gpu_avg_pct", "")),
        str(round(max(gpu_temps), 1) if gpu_temps else ""),
        str(payload.get("vram_avg_pct", "")),
        str((payload.get("power") or {}).get("current_w", "")),
        str((payload.get("power") or {}).get("energy_session_wh", "")),
        str(system.get("ram_pct", "")),
        str(system.get("cpu_pct", "")),
        str(cost.get("cost_per_hour", "")),
        str(cost.get("session_cost", "")),
    ]
