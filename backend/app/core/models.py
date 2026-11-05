"""Modelos de dominio (dataclasses tipados).

``TelemetryFrame`` es el snapshot completo que se envía por WebSocket y se guarda en
SQLite en cada tick. Todos los valores que pueden faltar son ``None`` para que la UI
muestre "sin datos" en lugar de romperse.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

from app.core.calculations import context_level


@dataclass(slots=True)
class GpuReading:
    """Lectura de una GPU individual. Cada campo ausente es ``None``."""

    index: int
    name: str
    vendor: str = "unknown"
    utilization_pct: float | None = None
    memory_used_mb: float | None = None
    memory_total_mb: float | None = None
    temperature_c: float | None = None
    fan_pct: float | None = None
    power_w: float | None = None
    power_limit_w: float | None = None
    # Derivados (calculados en __post_init__ para que ``asdict`` los serialice).
    memory_pct: float | None = field(init=False, default=None)
    power_pct: float | None = field(init=False, default=None)

    def __post_init__(self) -> None:
        if self.memory_used_mb is not None and self.memory_total_mb:
            self.memory_pct = round(min(100.0, self.memory_used_mb / self.memory_total_mb * 100.0), 2)
        if self.power_w is not None and self.power_limit_w:
            self.power_pct = round(min(100.0, self.power_w / self.power_limit_w * 100.0), 2)


@dataclass(slots=True)
class SystemReading:
    """Métricas de sistema (CPU, RAM, swap y uptime)."""

    cpu_pct: float | None = None
    cpu_count: int | None = None
    ram_used_gb: float | None = None
    ram_total_gb: float | None = None
    ram_pct: float | None = None
    swap_used_gb: float | None = None
    swap_total_gb: float | None = None
    swap_pct: float | None = None
    uptime_s: float | None = None


@dataclass(slots=True)
class RequestUsage:
    """Uso de una petición individual (usage de la API OpenAI)."""

    ts: float
    input_tokens: int
    output_tokens: int
    duration_s: float
    model: str | None = None
    # Derivados (calculados en __post_init__ para que ``asdict`` los serialice).
    total_tokens: int = field(init=False, default=0)
    tokens_per_second: float = field(init=False, default=0.0)

    def __post_init__(self) -> None:
        self.total_tokens = int(self.input_tokens + self.output_tokens)
        self.tokens_per_second = (
            round(self.output_tokens / self.duration_s, 2) if self.duration_s > 0 else 0.0
        )


@dataclass(slots=True)
class ContextState:
    """Estado de la ventana de contexto para la UI."""

    available: bool = False
    used_tokens: int | None = None
    max_tokens: int | None = None
    percent: float | None = None
    level: Literal["ok", "warning", "critical", "none"] = "none"
    source: str = "none"  # proxy | simulation | none


@dataclass(slots=True)
class TokensSnapshot:
    """Métricas agregadas de tokens y contexto de la fuente activa."""

    source: Literal["proxy", "prometheus", "simulation", "none"] = "none"
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    requests: int = 0
    instant_input_per_s: float = 0.0
    instant_output_per_s: float = 0.0
    moving_avg_output_per_s: float = 0.0
    last_request: RequestUsage | None = None
    recent_requests: list[RequestUsage] = field(default_factory=list)
    context: ContextState = field(default_factory=ContextState)


@dataclass(slots=True)
class InferenceStatus:
    """Estado de conexión con el servidor de inferencia."""

    status: Literal["online", "offline", "unknown"] = "unknown"
    engine: str = ""
    model: str = ""
    latency_ms: float | None = None
    error: str | None = None
    context_hint_tokens: int | None = None
    context_hint_source: str = ""


@dataclass(slots=True)
class PowerSnapshot:
    """Potencia eléctrica total (suma de GPUs)."""

    current_w: float | None = None
    limit_w: float | None = None
    percent: float | None = None
    energy_session_wh: float = 0.0
    energy_session_kwh: float = 0.0
    available: bool = False


@dataclass(slots=True)
class CostSnapshot:
    """Coste energético derivado del consumo + precio configurado."""

    price_per_kwh: float = 0.0
    session_cost: float = 0.0
    cost_per_hour: float | None = None
    projection_day: float | None = None
    projection_month: float | None = None
    cost_per_1k_tokens: float | None = None
    daily_cost: float = 0.0
    daily_limit: float | None = None
    daily_pct: float | None = None


@dataclass(slots=True)
class HardwareStatus:
    """Resumen del estado del hardware para la UI."""

    gpu_available: bool = False
    gpu_error: str | None = None
    provider: str = ""
    mode: Literal["simulation", "live"] = "live"


@dataclass(slots=True)
class AlertItem:
    """Alerta activa derivada de los umbrales configurados."""

    id: str
    severity: Literal["warning", "critical"]
    message: str
    value: float
    threshold: float
    ts: float

    def level(self) -> Literal["warning", "critical"]:
        return self.severity


@dataclass(slots=True)
class TelemetryFrame:
    """Snapshot completo de métricas de un tick. Se serializa con ``to_dict``."""

    ts: float
    ts_iso: str = ""
    mode: Literal["simulation", "live"] = "live"
    interval_s: float = 1.0
    tokens: TokensSnapshot = field(default_factory=TokensSnapshot)
    gpus: list[GpuReading] = field(default_factory=list)
    hardware: HardwareStatus = field(default_factory=HardwareStatus)
    power: PowerSnapshot = field(default_factory=PowerSnapshot)
    cost: CostSnapshot = field(default_factory=CostSnapshot)
    system: SystemReading = field(default_factory=SystemReading)
    inference: InferenceStatus = field(default_factory=InferenceStatus)
    alerts: list[AlertItem] = field(default_factory=list)
    gpu_avg_pct: float | None = None
    gpu_temp_max_c: float | None = None
    vram_avg_pct: float | None = None

    def to_dict(self) -> dict:
        """Serialización canónica usada por API, WebSocket y SQLite."""
        data = dataclasses.asdict(self)
        # El nivel/porcentaje de contexto se recalcula al construir el frame.
        return data


def utc_iso(ts: float) -> str:
    """Convierte epoch seconds a ISO-8601 UTC (opcional, para logs y CSV)."""
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_context(
    used: int | None, max_tokens: int | None, source: str
) -> ContextState:
    """Construye el estado de contexto completo (porcentaje + nivel de color)."""
    if used is None or not max_tokens or max_tokens <= 0:
        return ContextState(available=False, used_tokens=used, max_tokens=max_tokens, source=source)
    pct = min(100.0, used / max_tokens * 100.0)
    return ContextState(
        available=True,
        used_tokens=used,
        max_tokens=max_tokens,
        percent=round(pct, 2),
        level=context_level(pct),
        source=source,
    )
