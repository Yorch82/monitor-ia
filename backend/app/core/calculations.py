"""Funciones de cálculo puras (sin I/O, sin dependencias) — testables con pytest.

Todas las funciones son deterministas y devuelven ``None`` (o valor por defecto) cuando
faltan datos, para que la UI pueda mostrar "sin datos" en lugar de errores.
"""

from __future__ import annotations

import calendar
import time
from typing import Literal

Level = Literal["ok", "warning", "critical", "none"]


# ── Energía y coste ──────────────────────────────────────────────────────────


def energy_wh(power_w: float | None, dt_s: float) -> float:
    """Energía consumida en Wh entre dos muestras.

    E[W·h] = P[W] · Δt[s] / 3600. Si falta potencia o el intervalo no es válido → 0.
    """
    if power_w is None or dt_s <= 0:
        return 0.0
    return power_w * dt_s / 3600.0


def wh_to_kwh(wh: float) -> float:
    return wh / 1000.0


def kwh_cost(kwh: float, price_per_kwh: float) -> float:
    """Coste en € de una cantidad de kWh (0 y None-safe)."""
    if kwh < 0:
        return 0.0
    return max(0.0, kwh * price_per_kwh)


def session_cost_eur(energy_wh: float, price_per_kwh: float) -> float:
    """Coste de la energía acumulada de la sesión."""
    return round(kwh_cost(wh_to_kwh(energy_wh), price_per_kwh), 4)


def cost_per_hour(power_w: float | None, price_per_kwh: float) -> float | None:
    """Coste por hora si el consumo actual (W) se mantuviera constante."""
    if power_w is None:
        return None
    kwh_h = power_w / 1000.0
    return round(kwh_cost(kwh_h, price_per_kwh), 4)


def projected_costs(
    cost_hour: float | None,
) -> tuple[float | None, float | None]:
    """Proyección lineal (día, mes) según el ritmo actual de coste por hora."""
    if cost_hour is None:
        return None, None
    return round(cost_hour * 24, 2), round(cost_hour * 24 * 30, 2)


def cost_per_1k_tokens(session_cost: float, generated_tokens: int) -> float | None:
    """Coste por cada 1.000 tokens generados. ``None`` si aún no hay tokens."""
    if generated_tokens <= 0 or session_cost <= 0:
        return None
    return round(session_cost / (generated_tokens / 1000.0), 5)


def start_of_day_ts(now: float | None = None) -> float:
    """Epoch seconds del inicio del día local (00:00) — para el coste diario."""
    lt = time.localtime(now if now is not None else time.time())
    return time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1))


def day_key(now: float | None = None) -> str:
    """Clave 'YYYY-MM-DD' del día local (usada en webhooks/logs)."""
    lt = time.localtime(now if now is not None else time.time())
    return time.strftime("%Y-%m-%d", lt)


# ── Contexto ────────────────────────────────────────────────────────────────


def context_percent(used: int | None, max_tokens: int | None) -> float | None:
    """Ocupación de la ventana de contexto en % (None si faltan datos)."""
    if used is None or not max_tokens or max_tokens <= 0:
        return None
    return round(min(1000.0, (used / max_tokens) * 100.0), 2)


def context_level(percent: float | None) -> Level:
    """Nivel de color: verde < 70 %, ámbar 70-90 %, rojo > 90 %."""
    if percent is None:
        return "none"
    if percent > 90:
        return "critical"
    if percent >= 70:
        return "warning"
    return "ok"


def clamp_pct(value: float | None) -> float | None:
    """Recorta un porcentaje al rango [0, 100] para gauges/barras."""
    if value is None:
        return None
    return round(max(0.0, min(100.0, value)), 2)


# ── Utilidades de nivel para gauges ─────────────────────────────────────────


def bucket_level(percent: float | None, warn: float = 70.0, crit: float = 90.0) -> Level:
    """Nivel genérico para gauges (GPU, potencia, RAM)."""
    if percent is None:
        return "none"
    if percent > crit:
        return "critical"
    if percent >= warn:
        return "warning"
    return "ok"
