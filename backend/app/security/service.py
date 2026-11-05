"""Servicio de seguridad: parseo incremental de logs, GeoIP y snapshot agregado.

Flujo:
1. El middleware ``SecurityRecorder`` encola peticiones HTTP sospechosas.
2. Cada 5 s el servicio drena la cola y lee las líneas nuevas de los logs del host
   (offsets persistidos en SQLite para sobrevivir reinicios y rotaciones).
3. Los eventos se guardan y se enriquecen IPs con GeoIP (ip-api.com, caché 30 días).
4. ``snapshot()`` devuelve todo agregado para la pestaña Seguridad.
"""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Any

import httpx

from app.config import AppConfig
from app.security.middleware import SecurityRecorder
from app.security.parsers import (
    SecurityEventDraft,
    is_private_ip,
    parse_nginx_line,
    parse_ssh_line,
    parse_ufw_line,
)
from app.storage.database import SECURITY_RANGES, HistoryStore

log = logging.getLogger(__name__)

POLL_INTERVAL_S = 5.0
LOGS_POLL_INTERVAL_S = 5.0
INITIAL_TAIL_BYTES = 256 * 1024  # al arrancar se lee el final del log, no todo el histórico
MAX_EVENTS_PER_POLL = 400
GEO_CACHE_DAYS = 30
GEO_FAILURE_RETRY_S = 3600
GEO_MAX_PER_CYCLE = 2  # ip-api gratuito ≈45 req/min; 2 cada 5 s = 24/min


class SecurityService:
    """Tarea async de recolección + API de consulta de seguridad."""

    def __init__(
        self,
        config: AppConfig,
        store: HistoryStore,
        client: httpx.AsyncClient,
        recorder: SecurityRecorder,
    ) -> None:
        self.config = config
        self.store = store
        self.client = client
        self.recorder = recorder
        self.enabled = config.security_enabled
        self.geo_enabled = config.geoip_enabled
        self.retention_hours = config.security_retention_hours
        self.log_paths = config.security_path_list

        self._task: asyncio.Task | None = None
        self._last_log_poll = 0.0
        self._last_prune = 0.0
        self._geo_inflight = False
        self._stats = {"lookups_ok": 0, "lookups_failed": 0}
        self._log_status: dict[str, dict[str, Any]] = {
            p: {"exists": Path(p).exists(), "error": None if Path(p).exists() else "No existe"}
            for p in self.log_paths
        }

    # ── ciclo de vida ────────────────────────────────────────────────────────

    async def start(self) -> None:
        if not self.enabled:
            log.info("Monitor de seguridad desactivado (SECURITY_ENABLED=false)")
            return
        self._task = asyncio.create_task(self._loop(), name="security-monitor")
        log.info("Monitor de seguridad iniciado (%d fuentes de logs)", len(self.log_paths))

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _loop(self) -> None:
        while True:
            try:
                await self.poll()
            except Exception as exc:  # noqa: BLE001 — un poll fallido no debe tumbar el servicio
                log.warning("SecurityService: %s", exc)
            await asyncio.sleep(POLL_INTERVAL_S)

    async def poll(self) -> None:
        if not self.enabled:
            return
        now = time.time()

        # 1) Eventos HTTP capturados por el middleware
        http_events = self.recorder.drain()
        if http_events:
            self.store.insert_security_events([_to_row(e) for e in http_events])

        # 2) Logs del host (con throttle)
        if now - self._last_log_poll >= LOGS_POLL_INTERVAL_S:
            self._last_log_poll = now
            events = self._read_logs(now)
            if events:
                self.store.insert_security_events([_to_row(e) for e in events])
                log.info("Seguridad: %d eventos nuevos de logs", len(events))

        # 3) GeoIP (asíncrono, limitado por tasa)
        await self._enrich_geo(now)

        # 4) Retención
        if now - self._last_prune > 3600:
            self._last_prune = now
            pruned = self.store.prune_security(self.retention_hours)
            if pruned:
                log.info("Seguridad: %d eventos antiguos podados", pruned)

    # ── lectura incremental de logs ─────────────────────────────────────────

    def _read_logs(self, now: float) -> list[SecurityEventDraft]:
        events: list[SecurityEventDraft] = []
        for path_str in self.log_paths:
            path = Path(path_str)
            status = self._log_status.setdefault(path_str, {"exists": False, "error": None})
            if not path.exists():
                status.update(exists=False, error="No existe (¿volumen /var/log montado?)")
                continue
            status.update(exists=True, error=None)
            try:
                parser = _parser_for(path.name)
                lines = _read_new_lines(self.store, path)
                for line in lines:
                    event = parser(line, now)
                    if event:
                        events.append(event)
                    if len(events) >= MAX_EVENTS_PER_POLL:
                        break
            except OSError as exc:
                status.update(error=f"No se pudo leer: {exc}")
                log.warning("Seguridad: error leyendo %s: %s", path, exc)
            if len(events) >= MAX_EVENTS_PER_POLL:
                break
        return events

    # ── GeoIP ────────────────────────────────────────────────────────────────

    async def _enrich_geo(self, now: float) -> None:
        if not self.geo_enabled or self._geo_inflight:
            return
        pending = self.store.security_unenriched_ips(limit=40, failure_retry_ts=now - GEO_FAILURE_RETRY_S)
        if not pending:
            return

        # Las IPs privadas se marcan como "Red local" sin llamada externa.
        private = [ip for ip in pending if is_private_ip(ip)]
        for ip in private:
            self.store.security_geo_upsert(
                ip=ip, country_code="--", country="Red local", city="", isp="Privada",
                hosting=False, ts=now,
            )

        public = [ip for ip in pending if not is_private_ip(ip)][:GEO_MAX_PER_CYCLE]
        if not public:
            return
        self._geo_inflight = True
        try:
            for ip in public:
                await self._lookup_ip(ip, now)
        finally:
            self._geo_inflight = False

    async def _lookup_ip(self, ip: str, now: float) -> None:
        url = (
            f"http://ip-api.com/json/{ip}"
            "?fields=status,message,country,countryCode,city,isp,hosting"
        )
        try:
            resp = await self.client.get(url, timeout=3.0)
            data = resp.json() if resp.status_code == 200 else {}
        except Exception:  # noqa: BLE001 — GeoIP es opcional
            data = {}
        if data.get("status") == "success":
            self._stats["lookups_ok"] += 1
            self.store.security_geo_upsert(
                ip=ip,
                country_code=(data.get("countryCode") or "??")[:2],
                country=data.get("country") or "Desconocido",
                city=data.get("city") or "",
                isp=data.get("isp") or "",
                hosting=bool(data.get("hosting")),
                ts=now,
            )
        else:
            self._stats["lookups_failed"] += 1
            self.store.security_geo_upsert(
                ip=ip, country_code="??", country="Desconocido", city="", isp="",
                hosting=False, ts=now,
            )

    # ── API ──────────────────────────────────────────────────────────────────

    def snapshot(self, range_key: str = "24h") -> dict[str, Any]:
        """Snapshot agregado para la pestaña Seguridad."""
        if range_key not in SECURITY_RANGES:
            raise ValueError(f"Rango de seguridad inválido: {range_key}")

        if not self.enabled:
            return {
                "generated_at": time.time(),
                "range": range_key,
                "enabled": False,
                "sources": self._sources_status(),
                "summary": _empty_summary(),
                "timeline": [],
                "top_ips": [],
                "top_countries": [],
                "top_usernames": [],
                "top_ports": [],
                "top_paths": [],
                "recent_events": [],
            }

        data = self.store.security_snapshot(range_key)
        data.update(
            generated_at=time.time(),
            range=range_key,
            enabled=True,
            sources=self._sources_status(),
        )
        return data

    def _sources_status(self) -> dict[str, Any]:
        ssh_paths = [p for p in self.log_paths if Path(p).name in ("auth.log", "secure", "auth.log.1")]
        ufw_paths = [p for p in self.log_paths if "ufw" in Path(p).name]
        web_paths = [p for p in self.log_paths if "nginx" in p or "security.log" in Path(p).name]
        ssh_ok = any(self._log_status.get(p, {}).get("exists") for p in ssh_paths)
        ufw_ok = any(self._log_status.get(p, {}).get("exists") for p in ufw_paths)
        web_ok = any(self._log_status.get(p, {}).get("exists") for p in web_paths)
        return {
            "enabled": self.enabled,
            "ssh": {
                "available": ssh_ok,
                "paths": ssh_paths,
                "error": None if ssh_ok else "Monta /var/log del host para leer auth.log/secure",
            },
            "firewall": {
                "available": ufw_ok,
                "paths": ufw_paths,
                "error": None if ufw_ok else "Activa 'sudo ufw logging on' y monta /var/log",
            },
            "web": {
                "available": web_ok,
                "paths": web_paths,
                "error": None if web_ok else "El volumen nginx-logs no está montado",
            },
            "geoip": {
                "enabled": self.geo_enabled,
                "provider": "ip-api.com",
                "lookups_ok": self._stats["lookups_ok"],
                "lookups_failed": self._stats["lookups_failed"],
            },
            "retention_hours": self.retention_hours,
        }


# ── helpers ──────────────────────────────────────────────────────────────────


def _parser_for(filename: str):
    """Devuelve el parser adecuado según el nombre del fichero de log."""
    name = filename.lower()
    if "ufw" in name:
        return parse_ufw_line
    if "nginx" in name or name.endswith("security.log"):
        return parse_nginx_line
    return parse_ssh_line


def _read_new_lines(store: HistoryStore, path: Path) -> list[str]:
    """Lee desde el offset guardado. En el primer arranque empieza por el final."""
    size = path.stat().st_size
    offset = store.get_security_offset(str(path))
    if offset is None:
        offset = max(0, size - INITIAL_TAIL_BYTES)
    if size < offset:  # rotación del log
        offset = 0
    if size == offset:
        return []
    with path.open("rb") as fh:
        fh.seek(offset)
        data = fh.read(MAX_EVENTS_PER_POLL * 1024)
    new_offset = offset + len(data)
    # Si cortamos a mitad de línea, retrocede hasta el último \n leído.
    last_newline = data.rfind(b"\n")
    if last_newline != -1:
        data = data[: last_newline + 1]
        new_offset = offset + last_newline + 1
    store.set_security_offset(str(path), new_offset)
    return data.decode("utf-8", "replace").splitlines()


def _to_row(event: SecurityEventDraft) -> dict[str, Any]:
    return {
        "ts": event.ts,
        "kind": event.kind,
        "ip": event.ip,
        "classification": event.classification,
        "severity": event.severity,
        "username": event.username,
        "path": event.path,
        "user_agent": event.user_agent,
        "port": event.port,
        "detail": event.detail,
    }


def _empty_summary() -> dict[str, Any]:
    return {
        "total_events": 0,
        "ssh_failed": 0,
        "ssh_success": 0,
        "ssh_scan": 0,
        "firewall_blocks": 0,
        "web_suspicious": 0,
        "unique_ips": 0,
        "countries": 0,
        "bots": 0,
        "humans": 0,
        "unknown": 0,
        "bot_pct": None,
        "events_per_hour": 0.0,
        "last_ssh_success": None,
        "top_port": None,
        "top_country": None,
    }
