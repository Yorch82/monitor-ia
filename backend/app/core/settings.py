"""Settings runtime editables desde la UI y persistidos en SQLite.

Los *valores por defecto* vienen del .env (``AppConfig``); el estado guardado en la
base de datos tiene prioridad sobre .env para que los cambios de la página de Ajustes
sobrevivan a reinicios. Son dataclasses inmutables (``frozen=True``): cada update
sustituye la referencia completa, lo que hace el hot-reload trivial y sin bloqueos.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from typing import Any, Callable

from app.config import AppConfig
from app.core.calculations import clamp_pct  # noqa: F401  (re-export para tests)

TOKEN_SOURCES = ("auto", "proxy", "prometheus", "none")
GPU_PROVIDERS = ("auto", "nvidia", "amd", "apple", "none")


@dataclass(frozen=True)
class AlertThresholds:
    """Umbrales de alerta configurables por el usuario."""

    context_pct: float = 90.0
    gpu_temp_c: float = 80.0
    vram_pct: float = 95.0
    ram_pct: float = 90.0
    daily_cost_eur: float = 1.0

    def to_dict(self) -> dict[str, float]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: Any) -> "AlertThresholds":
        raw = raw or {}
        return cls(
            context_pct=_bounded_float(raw.get("context_pct", 90.0), 50, 100, 90.0),
            gpu_temp_c=_bounded_float(raw.get("gpu_temp_c", 80.0), 40, 110, 80.0),
            vram_pct=_bounded_float(raw.get("vram_pct", 95.0), 50, 100, 95.0),
            ram_pct=_bounded_float(raw.get("ram_pct", 90.0), 50, 100, 90.0),
            daily_cost_eur=_bounded_float(raw.get("daily_cost_eur", 1.0), 0, 10_000, 1.0),
        )


@dataclass(frozen=True)
class RuntimeSettings:
    """Configuración viva del sampler/monitor (sustituye la referencia en cada update)."""

    simulation_mode: bool
    refresh_interval_s: float
    price_per_kwh: float
    inference_base_url: str
    inference_metrics_url: str
    inference_api_key: str
    inference_model: str
    context_window: int
    token_source: str
    gpu_provider: str
    webhook_url: str
    history_retention_hours: int
    thresholds: AlertThresholds

    # ── serialización pública (nunca expone la API key) ───────────────────────
    def to_public_dict(self) -> dict[str, Any]:
        return {
            "simulation_mode": self.simulation_mode,
            "refresh_interval_ms": int(self.refresh_interval_s * 1000),
            "price_per_kwh": self.price_per_kwh,
            "inference_base_url": self.inference_base_url,
            "inference_metrics_url": self.inference_metrics_url,
            "inference_api_key_set": bool(self.inference_api_key),
            "inference_model": self.inference_model,
            "context_window": self.context_window,
            "token_source": self.token_source,
            "gpu_provider": self.gpu_provider,
            "webhook_url": self.webhook_url,
            "history_retention_hours": self.history_retention_hours,
            "thresholds": self.thresholds.to_dict(),
        }

    def to_persisted_dict(self) -> dict[str, Any]:
        """Serialización completa para SQLite (incluye la API key en claro)."""
        d = asdict(self)
        return d

    @classmethod
    def from_config(
        cls, config: AppConfig, persisted: dict[str, Any] | None = None
    ) -> "RuntimeSettings":
        """Defaults desde .env, sobrescritos por el estado persistido en SQLite."""
        base = cls(
            simulation_mode=bool(config.simulation_mode),
            refresh_interval_s=_bounded_float(config.refresh_interval_ms, 250, 60_000, 1000) / 1000,
            price_per_kwh=_bounded_float(config.kwh_price_eur, 0, 100, 0.15),
            inference_base_url=_clean_url(config.inference_base_url),
            inference_metrics_url=_clean_url(config.inference_metrics_url),
            inference_api_key=config.inference_api_key,
            inference_model=config.inference_model or "local-model",
            context_window=int(_bounded_float(config.context_window, 256, 2_000_000, 8192)),
            token_source=config.token_source if config.token_source in TOKEN_SOURCES else "auto",
            gpu_provider=config.gpu_provider if config.gpu_provider in GPU_PROVIDERS else "auto",
            webhook_url=config.webhook_url,
            history_retention_hours=int(_bounded_float(config.history_retention_hours, 1, 336, 24)),
            thresholds=AlertThresholds(
                context_pct=_bounded_float(config.alert_context_pct, 50, 100, 90),
                gpu_temp_c=_bounded_float(config.alert_gpu_temp_c, 40, 110, 80),
                vram_pct=_bounded_float(config.alert_vram_pct, 50, 100, 95),
                ram_pct=_bounded_float(config.alert_ram_pct, 50, 100, 90),
                daily_cost_eur=_bounded_float(config.alert_daily_cost_eur, 0, 10_000, 1.0),
            ),
        )
        if persisted:
            return base.apply_update(persisted)
        return base

    def apply_update(self, raw: Any) -> "RuntimeSettings":
        """Aplica un update parcial validando y acotando cada campo (nunca muta self)."""
        raw = raw or {}
        th = raw.get("thresholds")
        new_thresholds = self.thresholds.from_dict(th) if isinstance(th, dict) else self.thresholds

        interval_ms = self.refresh_interval_s * 1000
        interval_ms = _bounded_float(
            raw.get("refresh_interval_ms", interval_ms), 250, 60_000, interval_ms
        )

        values: dict[str, Any] = {
            "simulation_mode": self.simulation_mode if "simulation_mode" not in raw else bool(raw["simulation_mode"]),
            "refresh_interval_s": interval_ms / 1000,
            "price_per_kwh": _bounded_float(raw.get("price_per_kwh", self.price_per_kwh), 0, 100, self.price_per_kwh),
            "inference_base_url": _clean_url(raw.get("inference_base_url", self.inference_base_url)) or "",
            "inference_metrics_url": _clean_url(raw.get("inference_metrics_url", self.inference_metrics_url)) or "",
            "inference_api_key": raw.get("inference_api_key", self.inference_api_key) or "",
            "inference_model": str(raw.get("inference_model", self.inference_model) or "local-model"),
            "context_window": int(_bounded_float(raw.get("context_window", self.context_window), 256, 2_000_000, self.context_window)),
            "token_source": _enum(raw.get("token_source", self.token_source), TOKEN_SOURCES, self.token_source),
            "gpu_provider": _enum(raw.get("gpu_provider", self.gpu_provider), GPU_PROVIDERS, self.gpu_provider),
            "webhook_url": _clean_url(raw.get("webhook_url", self.webhook_url)) or "",
            "history_retention_hours": int(_bounded_float(raw.get("history_retention_hours", self.history_retention_hours), 1, 336, self.history_retention_hours)),
            "thresholds": new_thresholds,
        }
        return replace(self, **values)


class SettingsManager:
    """Contenedor del settings vivo; swap atómico de referencia al aplicar updates."""

    def __init__(
        self,
        initial: RuntimeSettings,
        on_change: Callable[[RuntimeSettings], None] | None = None,
    ) -> None:
        self._settings = initial
        self._on_change = on_change

    def get(self) -> RuntimeSettings:
        return self._settings

    def update(self, new_settings: RuntimeSettings) -> None:
        self._settings = new_settings
        if self._on_change:
            self._on_change(new_settings)


# ── helpers de validación ────────────────────────────────────────────────────


def _bounded_float(value: Any, low: float, high: float, default: float) -> float:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return default
    return min(high, max(low, f))


def _enum(value: Any, options: tuple[str, ...], default: str) -> str:
    return str(value) if value in options else default


def _clean_url(value: Any) -> str:
    url = str(value or "").strip().rstrip("/")
    return url
