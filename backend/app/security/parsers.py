"""Parsers de eventos de seguridad (puros, sin I/O) — testables con pytest.

Formatos soportados:
- SSH (Debian/Ubuntu ``auth.log`` y RHEL ``secure``): intentos fallidos, logins
  aceptados, escaneos ("Unable to negotiate", "Bad protocol version").
- Firewall ``ufw.log``: bloqueos ``[UFW BLOCK]`` con IP origen y puerto destino.
- Nginx access log (formato ``security`` definido en ``frontend/nginx.conf``):
  se emiten solo rutas sospechosas o sondeos a la API.

La clasificación bot/humano se hace con heurísticas (patrones de user-agent y
rutas típicas de escáneres, además de que todo fallo SSH se considera automatizado).
"""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from typing import Literal

Classification = Literal["bot", "human", "unknown"]
Severity = Literal["info", "warning", "critical"]


@dataclass(frozen=True, slots=True)
class SecurityEventDraft:
    """Evento de seguridad normalizado, listo para persistir."""

    ts: float
    kind: str  # ssh_failed | ssh_success | ssh_scan | firewall_block | http_suspicious
    ip: str
    classification: Classification
    severity: Severity
    username: str | None = None
    path: str | None = None
    user_agent: str | None = None
    port: int | None = None
    detail: str = ""


# ── SSH ──────────────────────────────────────────────────────────────────────

_SSH_FAILED = re.compile(
    r"Failed password for (?:invalid user )?(?P<user>\S+) from (?P<ip>[0-9a-fA-F:.]+) port \d+"
)
_SSH_ACCEPTED = re.compile(
    r"Accepted \S+ for (?P<user>\S+) from (?P<ip>[0-9a-fA-F:.]+) port \d+"
)
_SSH_MAX_ATTEMPTS = re.compile(
    r"maximum authentication attempts exceeded for (?:invalid user )?(?P<user>\S+) "
    r"from (?P<ip>[0-9a-fA-F:.]+) port"
)
_SSH_NEGOTIATE = re.compile(r"Unable to negotiate with (?P<ip>[0-9a-fA-F:.]+) port")
_SSH_BAD_PROTO = re.compile(
    r"Bad protocol version identification .* from (?P<ip>[0-9a-fA-F:.]+) port"
)


def parse_ssh_line(line: str, now: float) -> SecurityEventDraft | None:
    """Convierte una línea de auth.log/secure en un evento (si es relevante)."""
    match = _SSH_FAILED.search(line)
    if match:
        return SecurityEventDraft(
            ts=now, kind="ssh_failed", ip=match.group("ip"), classification="bot",
            severity="info", username=match.group("user"),
            detail=f"Contraseña fallida para '{match.group('user')}'",
        )
    match = _SSH_ACCEPTED.search(line)
    if match:
        return SecurityEventDraft(
            ts=now, kind="ssh_success", ip=match.group("ip"), classification="human",
            severity="warning", username=match.group("user"),
            detail=f"Login SSH aceptado para '{match.group('user')}'",
        )
    match = _SSH_MAX_ATTEMPTS.search(line)
    if match:
        return SecurityEventDraft(
            ts=now, kind="ssh_failed", ip=match.group("ip"), classification="bot",
            severity="info", username=match.group("user"),
            detail="Máximo de intentos de autenticación excedido",
        )
    match = _SSH_NEGOTIATE.search(line) or _SSH_BAD_PROTO.search(line)
    if match:
        return SecurityEventDraft(
            ts=now, kind="ssh_scan", ip=match.group("ip"), classification="bot",
            severity="warning", detail="Escaneo/negociación SSH inválida",
        )
    return None


# ── UFW ──────────────────────────────────────────────────────────────────────

_UFW_SRC = re.compile(r"\[UFW (?:BLOCK|AUDIT)\].*?SRC=(?P<ip>[0-9a-fA-F:.]+)")
_UFW_DPT = re.compile(r"DPT=(?P<port>\d+)")
_UFW_PROTO = re.compile(r"PROTO=(?P<proto>\w+)")


def parse_ufw_line(line: str, now: float) -> SecurityEventDraft | None:
    """Extrae bloqueos de ufw (intentos de conexión a puertos cerrados)."""
    if "UFW BLOCK" not in line and "UFW AUDIT" not in line:
        return None
    src = _UFW_SRC.search(line)
    if not src:
        return None
    port_match = _UFW_DPT.search(line)
    proto_match = _UFW_PROTO.search(line)
    ip = src.group("ip")
    port = int(port_match.group("port")) if port_match else None
    proto = proto_match.group("proto") if proto_match else "?"
    return SecurityEventDraft(
        ts=now, kind="firewall_block", ip=ip, classification="bot", severity="info",
        port=port, detail=f"Conexión bloqueada {proto} puerto {port or '?'}",
    )


# ── Nginx access log ─────────────────────────────────────────────────────────

_NGINX_LINE = re.compile(
    r'^(?P<ip>\S+) \S+ \S+ \[[^\]]+\] "(?P<method>[A-Z]+) (?P<path>\S+) [^"]*" '
    r'(?P<status>\d{3}) \S+ "[^"]*" "(?P<ua>[^"]*)"'
)

# Rutas típicas de escáneres / exploits. Case-insensitive.
SCAN_PATH_RE = re.compile(
    r"(?i)("
    r"\.env|\.git|\.aws|\.ssh|wp-admin|wp-login|wp-config|xmlrpc\.php|"
    r"phpmyadmin|pma/|myadmin|/etc/passwd|/\.\.|cgi-bin|actuator|server-status|"
    r"manager/html|/solr|/console|boaform|hnap1|sdk/weblanguage|\.php|\.asp|\.jsp|"
    r"\.sql|\.bak|/backup|/vendor/|/shell|/eval|/setup|/config|/owa/|"
    r"/autodiscover|/remote/login|/login\.action|/zabbix|/jenkins|/laravel|"
    r"/druid|/nacos|/telescope|/wp-json|/thinkphp|/struts|/login\.php|"
    r"/administrator|/admin/"
    r")"
)

BOT_UA_RE = re.compile(
    r"(?i)(bot|crawl|spider|scrapy|python-requests|python-urllib|aiohttp|httpx|"
    r"curl|wget|nmap|masscan|zgrab|nikto|sqlmap|go-http-client|java/|libwww|"
    r"okhttp|headless|phantom|selenium|axios|node-fetch|powershell|winhttp|"
    r"axios|postman|insomnia)"
)

_API_PROBE_STATUSES = {400, 401, 403, 404, 405}


def is_private_ip(ip: str) -> bool:
    """True para IPs no enrutables en Internet (loopback, LAN, CGNAT/Tailscale, reservadas)."""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return True
    return not addr.is_global


def is_bot_agent(user_agent: str | None) -> bool:
    return bool(BOT_UA_RE.search(user_agent or ""))


def is_scan_path(path: str) -> bool:
    return bool(SCAN_PATH_RE.search(path or ""))


def parse_nginx_line(line: str, now: float) -> SecurityEventDraft | None:
    """Emite eventos solo para rutas sospechosas o sondeos a la API."""
    match = _NGINX_LINE.match(line)
    if not match:
        return None
    path = match.group("path").split("?", 1)[0]
    status = int(match.group("status"))
    method = match.group("method")
    ua = match.group("ua")

    suspicious = is_scan_path(path)
    api_probe = path.startswith("/api/") and status in _API_PROBE_STATUSES
    if not suspicious and not api_probe:
        return None

    bot = suspicious or is_bot_agent(ua)
    detail = f"{method} {path} → HTTP {status}"
    return SecurityEventDraft(
        ts=now, kind="http_suspicious", ip=match.group("ip"),
        classification="bot" if bot else "unknown",
        severity="warning" if suspicious else "info",
        path=path, user_agent=ua[:300], detail=detail,
    )


def build_http_event(
    ts: float, ip: str, path: str, method: str, user_agent: str, status: int
) -> SecurityEventDraft:
    """Evento HTTP capturado directamente por el backend (rutas desconocidas)."""
    suspicious = is_scan_path(path)
    bot = suspicious or is_bot_agent(user_agent)
    return SecurityEventDraft(
        ts=ts, kind="http_suspicious", ip=ip,
        classification="bot" if bot else "unknown",
        severity="warning" if suspicious else "info",
        path=path, user_agent=(user_agent or "")[:300],
        detail=f"{method} {path} → HTTP {status}",
    )
