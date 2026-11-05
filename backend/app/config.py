"""Configuración del backend mediante variables de entorno (.env → pydantic-settings).

Solo define *valores por defecto*: el usuario puede ajustar después precio, intervalo,
umbrales, etc. desde la página de Ajustes (se persisten en SQLite y sobreviven a reinicios).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class AppConfig(BaseSettings):
    """Variables de entorno del proceso. Cualquiera de estas claves puede definirse en ``.env``."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ── Servidor ──────────────────────────────────────────────────────────────
    app_host: str = "0.0.0.0"
    app_port: int = 8000

    # ── Persistencia ──────────────────────────────────────────────────────────
    db_path: str = "./data/monitor.db"
    history_retention_hours: int = 24

    # ── CORS (orígenes separados por coma) ────────────────────────────────────
    cors_origins: str = (
        "http://localhost:5173,http://localhost:8080,"
        "http://192.168.1.35:8080,http://100.115.55.87:8080"
    )

    # ── Valores iniciales de settings runtime (editables desde la UI) ─────────
    simulation_mode: bool = True
    refresh_interval_ms: float = 1000
    kwh_price_eur: float = 0.15
    gpu_provider: str = "auto"  # auto | nvidia | amd | apple | none
    inference_base_url: str = "http://host.docker.internal:11434/v1"
    inference_metrics_url: str = ""  # vacío → se intenta {base}/metrics sin /v1
    inference_api_key: str = ""
    inference_model: str = "local-model"
    context_window: int = 8192
    token_source: str = "auto"  # auto | proxy | prometheus | none
    webhook_url: str = ""

    # ── Umbrales de alerta iniciales ─────────────────────────────────────────
    alert_context_pct: float = 90.0
    alert_gpu_temp_c: float = 80.0
    alert_vram_pct: float = 95.0
    alert_ram_pct: float = 90.0
    alert_daily_cost_eur: float = 1.0

    # ── Parámetros del modo simulación ───────────────────────────────────────
    sim_gpu_count: int = 1
    sim_power_limit_w: float = 450.0
    sim_vram_total_mb: float = 24576.0
    sim_ram_total_gb: float = 64.0

    # ── Seguridad ─────────────────────────────────────────────────────────────
    security_enabled: bool = True
    # Rutas de logs del host montadas en el contenedor (separadas por coma).
    #   auth.log/secure → SSH · ufw.log → firewall · nginx/security.log → escaneos web
    security_log_paths: str = (
        "/host/log/auth.log,/host/log/secure,"
        "/host/log/ufw.log,/host/nginx/security.log"
    )
    security_retention_hours: int = 168  # 7 días
    geoip_enabled: bool = True

    @property
    def security_path_list(self) -> list[str]:
        return [p.strip() for p in self.security_log_paths.split(",") if p.strip()]

    @property
    def db_file(self) -> Path:
        return Path(self.db_path)

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache(maxsize=1)
def get_config() -> AppConfig:
    """Instancia cacheada de la configuración (se lee .env una sola vez)."""
    return AppConfig()
