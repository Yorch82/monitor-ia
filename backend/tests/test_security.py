"""Tests de parsers de seguridad: SSH, UFW, nginx, GeoIP/privadas y clasificación."""

from app.security.parsers import (
    build_http_event,
    is_bot_agent,
    is_private_ip,
    is_scan_path,
    parse_nginx_line,
    parse_ssh_line,
    parse_ufw_line,
)

NOW = 1_700_000_000.0


def test_ssh_failed_password():
    line = (
        "Nov  5 12:34:56 claudio sshd[1234]: Failed password for invalid user admin "
        "from 203.0.113.7 port 54321 ssh2"
    )
    ev = parse_ssh_line(line, NOW)
    assert ev is not None
    assert ev.kind == "ssh_failed"
    assert ev.ip == "203.0.113.7"
    assert ev.username == "admin"
    assert ev.classification == "bot"


def test_ssh_accepted_login():
    line = (
        "Nov  5 12:35:01 claudio sshd[1234]: Accepted publickey for yorch "
        "from 192.168.1.20 port 51000 ssh2"
    )
    ev = parse_ssh_line(line, NOW)
    assert ev is not None
    assert ev.kind == "ssh_success"
    assert ev.classification == "human"
    assert ev.severity == "warning"


def test_ssh_scan_negotiate():
    line = "Nov  5 12:36:00 claudio sshd[1234]: Unable to negotiate with 198.51.100.9 port 4000: no matching key exchange method found"
    ev = parse_ssh_line(line, NOW)
    assert ev is not None
    assert ev.kind == "ssh_scan"
    assert ev.ip == "198.51.100.9"


def test_ssh_irrelevant_line():
    assert parse_ssh_line("Nov  5 12:37:00 claudio systemd[1]: Started Session 12", NOW) is None


def test_ufw_block():
    line = (
        "Nov  5 12:38:00 claudio kernel: [ 1234.567] [UFW BLOCK] IN=enp3s0 OUT= "
        "MAC=00:11:22:33:44:55 SRC=45.155.205.10 DST=192.168.1.35 LEN=44 "
        "PROTO=TCP SPT=50000 DPT=23 WINDOW=1024"
    )
    ev = parse_ufw_line(line, NOW)
    assert ev is not None
    assert ev.kind == "firewall_block"
    assert ev.ip == "45.155.205.10"
    assert ev.port == 23
    assert ev.classification == "bot"


def test_nginx_scan_path():
    line = (
        '203.0.113.50 - - [05/Nov/2026:12:39:00 +0000] "GET /.env HTTP/1.1" 200 '
        '512 "-" "Mozilla/5.0 zgrab/0.x"'
    )
    ev = parse_nginx_line(line, NOW)
    assert ev is not None
    assert ev.kind == "http_suspicious"
    assert ev.path == "/.env"
    assert ev.classification == "bot"


def test_nginx_normal_request_ignored():
    line = (
        '192.168.1.20 - - [05/Nov/2026:12:40:00 +0000] "GET /api/history?range=1m HTTP/1.1" '
        '200 1234 "-" "Mozilla/5.0"'
    )
    assert parse_nginx_line(line, NOW) is None


def test_nginx_api_probe():
    line = (
        '203.0.113.9 - - [05/Nov/2026:12:41:00 +0000] "POST /api/settings HTTP/1.1" '
        '403 200 "-" "python-requests/2.31"'
    )
    ev = parse_nginx_line(line, NOW)
    assert ev is not None
    assert ev.path == "/api/settings"
    assert ev.classification == "bot"


def test_private_and_public_ips():
    assert is_private_ip("192.168.1.35")
    assert is_private_ip("127.0.0.1")
    assert is_private_ip("172.18.0.5")
    assert is_private_ip("100.115.55.87")  # CGNAT/Tailscale
    assert is_private_ip("203.0.113.7")    # TEST-NET (no global)
    assert not is_private_ip("8.8.8.8")
    assert not is_private_ip("45.155.205.10")


def test_scan_paths_y_agentes_bot():
    assert is_scan_path("/wp-admin/setup-config.php")
    assert is_scan_path("/.git/config")
    assert not is_scan_path("/api/history")
    assert is_bot_agent("Mozilla/5.0 (compatible; Googlebot/2.1)")
    assert is_bot_agent("python-requests/2.31")
    assert not is_bot_agent("Mozilla/5.0 (Windows NT 10.0; Win64; x64) Firefox/138.0")


def test_build_http_event():
    ev = build_http_event(
        ts=NOW, ip="203.0.113.4", path="/administrator", method="GET",
        user_agent="Mozilla/5.0", status=404,
    )
    assert ev.kind == "http_suspicious"
    assert ev.classification == "bot"
    assert "HTTP 404" in ev.detail
