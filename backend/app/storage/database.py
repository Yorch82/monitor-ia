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

# Rangos de la pestaña Seguridad (más amplios, buckets de 2 min / 15 min / 1 h).
SECURITY_RANGES: dict[str, tuple[float, float]] = {
    "1h": (3600, 120),
    "24h": (86400, 900),
    "7d": (7 * 86400, 3600),
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
    energy_delta_wh REAL,
    payload TEXT
);
CREATE INDEX IF NOT EXISTS idx_samples_ts ON samples(ts);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- ── Seguridad ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS security_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    kind TEXT NOT NULL,
    ip TEXT NOT NULL,
    classification TEXT NOT NULL,
    severity TEXT NOT NULL,
    username TEXT,
    path TEXT,
    user_agent TEXT,
    port INTEGER,
    detail TEXT
);
CREATE INDEX IF NOT EXISTS idx_security_ts ON security_events(ts);
CREATE INDEX IF NOT EXISTS idx_security_ip ON security_events(ip);

CREATE TABLE IF NOT EXISTS security_geo (
    ip TEXT PRIMARY KEY,
    country_code TEXT,
    country TEXT,
    city TEXT,
    isp TEXT,
    hosting INTEGER DEFAULT 0,
    updated_at REAL
);

CREATE TABLE IF NOT EXISTS security_offsets (
    path TEXT PRIMARY KEY,
    offset INTEGER NOT NULL,
    updated_at REAL
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
        # Migración: bases creadas antes guardaban la energía acumulada (energy_wh)
        # y no la energía por muestra (energy_delta_wh). Añadimos la nueva columna.
        columns = {row[1] for row in self._conn.execute("PRAGMA table_info(samples)")}
        if "energy_delta_wh" not in columns:
            self._conn.execute("ALTER TABLE samples ADD COLUMN energy_delta_wh REAL")
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
        energy_delta_wh: float,
        ram_pct: float | None,
        cpu_pct: float | None,
        cost_per_hour: float | None,
    ) -> None:
        """Inserta la fila del tick (payload completo en JSON para CSV/futuras vistas)."""
        with self._lock:
            self._conn.execute(
                """INSERT INTO samples (ts, input_total, output_total, moving_avg_tps,
                   context_pct, gpu_pct, gpu_temp_c, vram_pct, power_w, energy_delta_wh,
                   ram_pct, cpu_pct, cost_per_hour, payload)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (ts, input_total, output_total, moving_avg_tps, context_pct, gpu_pct,
                 gpu_temp_c, vram_pct, power_w, energy_delta_wh, ram_pct, cpu_pct,
                 cost_per_hour, json.dumps(payload, ensure_ascii=False)),
            )
            self._conn.commit()

    def energy_since(self, ts_from: float) -> float:
        """Suma de energía Wh registrada desde una marca temporal (coste diario)."""
        with self._lock:
            row = self._conn.execute(
                "SELECT COALESCE(SUM(energy_delta_wh), 0) FROM samples WHERE ts >= ?", (ts_from,)
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

    # ── seguridad: eventos, offsets y geolocalización ──────────────────────

    def insert_security_events(self, events: list[dict[str, Any]]) -> None:
        """Inserta un lote de eventos de seguridad normalizados."""
        if not events:
            return
        with self._lock:
            self._conn.executemany(
                """INSERT INTO security_events
                   (ts, kind, ip, classification, severity, username, path, user_agent, port, detail)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                [
                    (
                        e["ts"], e["kind"], e["ip"], e["classification"], e["severity"],
                        e.get("username"), e.get("path"), e.get("user_agent"),
                        e.get("port"), e.get("detail") or "",
                    )
                    for e in events
                ],
            )
            self._conn.commit()

    def prune_security(self, retention_hours: int) -> int:
        cutoff = time.time() - retention_hours * 3600
        with self._lock:
            cur = self._conn.execute("DELETE FROM security_events WHERE ts < ?", (cutoff,))
            self._conn.commit()
        return max(0, cur.rowcount or 0)

    def get_security_offset(self, path: str) -> int | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT offset FROM security_offsets WHERE path = ?", (path,)
            ).fetchone()
        return int(row[0]) if row else None

    def set_security_offset(self, path: str, offset: int) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO security_offsets (path, offset, updated_at) VALUES (?,?,?) "
                "ON CONFLICT(path) DO UPDATE SET offset=excluded.offset, updated_at=excluded.updated_at",
                (path, offset, time.time()),
            )
            self._conn.commit()

    def security_geo_upsert(
        self, ip: str, country_code: str, country: str, city: str, isp: str,
        hosting: bool, ts: float,
    ) -> None:
        with self._lock:
            self._conn.execute(
                """INSERT INTO security_geo (ip, country_code, country, city, isp, hosting, updated_at)
                   VALUES (?,?,?,?,?,?,?)
                   ON CONFLICT(ip) DO UPDATE SET
                     country_code=excluded.country_code, country=excluded.country,
                     city=excluded.city, isp=excluded.isp, hosting=excluded.hosting,
                     updated_at=excluded.updated_at""",
                (ip, country_code, country, city, isp, int(hosting), ts),
            )
            self._conn.commit()

    def security_unenriched_ips(self, limit: int, failure_retry_ts: float) -> list[str]:
        """IPs con eventos y sin geolocalización (o con fallo caducado)."""
        with self._lock:
            rows = self._conn.execute(
                """SELECT e.ip, COUNT(*) AS c
                   FROM security_events e
                   LEFT JOIN security_geo g ON g.ip = e.ip
                   WHERE g.ip IS NULL
                      OR (g.country_code IN ('??', '') AND g.updated_at < ?)
                   GROUP BY e.ip
                   ORDER BY c DESC
                   LIMIT ?""",
                (failure_retry_ts, limit),
            ).fetchall()
        return [r[0] for r in rows]

    def security_snapshot(self, range_key: str) -> dict[str, Any]:
        """Agregados para la pestaña Seguridad (KPIs, timeline, tops y recientes)."""
        span, bucket = SECURITY_RANGES[range_key]
        now = time.time()
        since = now - span

        with self._lock:
            kind_rows = self._conn.execute(
                "SELECT kind, COUNT(*) FROM security_events WHERE ts >= ? GROUP BY kind",
                (since,),
            ).fetchall()
            totals_row = self._conn.execute(
                """SELECT COUNT(*), COUNT(DISTINCT e.ip), COUNT(DISTINCT g.country_code)
                   FROM security_events e LEFT JOIN security_geo g ON g.ip = e.ip
                   WHERE e.ts >= ?""",
                (since,),
            ).fetchone()
            class_rows = self._conn.execute(
                """SELECT cls, COUNT(*) FROM (
                     SELECT ip,
                       CASE WHEN SUM(CASE WHEN classification='bot' THEN 1 ELSE 0 END) > 0 THEN 'bot'
                            WHEN SUM(CASE WHEN classification='human' THEN 1 ELSE 0 END) > 0 THEN 'human'
                            ELSE 'unknown' END AS cls
                     FROM security_events WHERE ts >= ? GROUP BY ip
                   ) GROUP BY cls""",
                (since,),
            ).fetchall()
            timeline_rows = self._conn.execute(
                f"""SELECT (CAST(ts / {bucket} AS INTEGER) * {bucket}) AS bts, kind, COUNT(*)
                    FROM security_events WHERE ts >= ? GROUP BY bts, kind ORDER BY bts""",
                (since,),
            ).fetchall()
            top_ips = self._conn.execute(
                """SELECT e.ip, COUNT(*) AS events, MAX(e.ts) AS last_ts, MIN(e.ts) AS first_ts,
                          SUM(CASE WHEN e.kind='ssh_failed' THEN 1 ELSE 0 END),
                          SUM(CASE WHEN e.kind='ssh_success' THEN 1 ELSE 0 END),
                          SUM(CASE WHEN e.kind='ssh_scan' THEN 1 ELSE 0 END),
                          SUM(CASE WHEN e.kind='firewall_block' THEN 1 ELSE 0 END),
                          SUM(CASE WHEN e.kind='http_suspicious' THEN 1 ELSE 0 END),
                          MAX(g.country_code), MAX(g.country), MAX(g.city), MAX(g.isp),
                          CASE
                            WHEN SUM(CASE WHEN e.classification='bot' THEN 1 ELSE 0 END) > 0 THEN 'bot'
                            WHEN SUM(CASE WHEN e.classification='human' THEN 1 ELSE 0 END) > 0 THEN 'human'
                            ELSE 'unknown'
                          END
                   FROM security_events e LEFT JOIN security_geo g ON g.ip = e.ip
                   WHERE e.ts >= ?
                   GROUP BY e.ip ORDER BY events DESC LIMIT 10""",
                (since,),
            ).fetchall()
            top_countries = self._conn.execute(
                """SELECT COALESCE(g.country_code, '??') AS cc,
                          COALESCE(g.country, 'Desconocido') AS country,
                          COUNT(*) AS events, COUNT(DISTINCT e.ip) AS ips
                   FROM security_events e LEFT JOIN security_geo g ON g.ip = e.ip
                   WHERE e.ts >= ? GROUP BY cc ORDER BY events DESC LIMIT 8""",
                (since,),
            ).fetchall()
            top_usernames = self._conn.execute(
                """SELECT username, COUNT(*) AS events FROM security_events
                   WHERE ts >= ? AND username IS NOT NULL AND username != ''
                   GROUP BY username ORDER BY events DESC LIMIT 8""",
                (since,),
            ).fetchall()
            top_ports = self._conn.execute(
                """SELECT port, COUNT(*) AS events FROM security_events
                   WHERE ts >= ? AND port IS NOT NULL
                   GROUP BY port ORDER BY events DESC LIMIT 8""",
                (since,),
            ).fetchall()
            top_paths = self._conn.execute(
                """SELECT path, COUNT(*) AS events FROM security_events
                   WHERE ts >= ? AND path IS NOT NULL AND path != ''
                   GROUP BY path ORDER BY events DESC LIMIT 8""",
                (since,),
            ).fetchall()
            last_success = self._conn.execute(
                """SELECT e.ts, e.ip, e.username, g.country_code, g.country
                   FROM security_events e LEFT JOIN security_geo g ON g.ip = e.ip
                   WHERE e.kind = 'ssh_success' AND e.ts >= ?
                   ORDER BY e.ts DESC LIMIT 1""",
                (since,),
            ).fetchone()
            recent = self._conn.execute(
                """SELECT e.ts, e.kind, e.ip, e.classification, e.severity, e.username,
                          e.path, e.port, e.detail, e.user_agent,
                          g.country_code, g.country, g.city
                   FROM security_events e LEFT JOIN security_geo g ON g.ip = e.ip
                   WHERE e.ts >= ? ORDER BY e.ts DESC LIMIT 30""",
                (since,),
            ).fetchall()

        kinds = {row[0]: int(row[1]) for row in kind_rows}
        total_events, unique_ips, countries = (
            (int(totals_row[0]), int(totals_row[1]), int(totals_row[2])) if totals_row else (0, 0, 0)
        )
        classes = {row[0]: int(row[1]) for row in class_rows}
        bots = classes.get("bot", 0)
        humans = classes.get("human", 0)
        unknown = classes.get("unknown", 0)
        known_agents = bots + humans + unknown

        timeline_map: dict[int, dict[str, Any]] = {}
        for bts, kind, count in timeline_rows:
            point = timeline_map.setdefault(
                int(bts),
                {"t": int(bts) * 1000, "ssh_failed": 0, "ssh_success": 0,
                 "ssh_scan": 0, "firewall_blocks": 0, "web_suspicious": 0},
            )
            key = {
                "ssh_failed": "ssh_failed", "ssh_success": "ssh_success",
                "ssh_scan": "ssh_scan", "firewall_block": "firewall_blocks",
                "http_suspicious": "web_suspicious",
            }.get(kind, kind)
            if key in point:
                point[key] += int(count)

        ports = [{"port": int(p), "attempts": int(c)} for p, c in top_ports]
        top_country_rows = [
            {"country_code": cc, "country": c, "events": int(ev), "ips": int(ips)}
            for cc, c, ev, ips in top_countries
        ]

        return {
            "summary": {
                "total_events": total_events,
                "ssh_failed": kinds.get("ssh_failed", 0),
                "ssh_success": kinds.get("ssh_success", 0),
                "ssh_scan": kinds.get("ssh_scan", 0),
                "firewall_blocks": kinds.get("firewall_block", 0),
                "web_suspicious": kinds.get("http_suspicious", 0),
                "unique_ips": unique_ips,
                "countries": countries,
                "bots": bots,
                "humans": humans,
                "unknown": unknown,
                "bot_pct": round(bots / known_agents * 100, 1) if known_agents else None,
                "events_per_hour": round(total_events / max(span / 3600, 1e-9), 2),
                "last_ssh_success": (
                    {
                        "ts": last_success[0], "ip": last_success[1],
                        "username": last_success[2],
                        "country_code": last_success[3], "country": last_success[4],
                    }
                    if last_success else None
                ),
                "top_port": ports[0] if ports else None,
                "top_country": top_country_rows[0] if top_country_rows else None,
            },
            "timeline": [timeline_map[k] for k in sorted(timeline_map)],
            "top_ips": [
                {
                    "ip": ip, "events": int(events), "last_ts": last_ts, "first_ts": first_ts,
                    "ssh_failed": int(ssh_failed), "ssh_success": int(ssh_success),
                    "ssh_scan": int(ssh_scan), "firewall_blocks": int(firewall_blocks),
                    "web_suspicious": int(web_suspicious),
                    "country_code": cc, "country": country, "city": city, "isp": isp,
                    "classification": cls,
                }
                for (ip, events, last_ts, first_ts, ssh_failed, ssh_success, ssh_scan,
                     firewall_blocks, web_suspicious, cc, country, city, isp, cls) in top_ips
            ],
            "top_countries": top_country_rows,
            "top_usernames": [{"username": u, "attempts": int(c)} for u, c in top_usernames],
            "top_ports": ports,
            "top_paths": [{"path": p, "attempts": int(c)} for p, c in top_paths],
            "recent_events": [
                {
                    "ts": ts, "kind": kind, "ip": ip, "classification": cls,
                    "severity": severity, "username": username, "path": path,
                    "port": port, "detail": detail, "user_agent": ua,
                    "country_code": cc, "country": country, "city": city,
                }
                for (ts, kind, ip, cls, severity, username, path, port, detail, ua,
                     cc, country, city) in recent
            ],
        }

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
