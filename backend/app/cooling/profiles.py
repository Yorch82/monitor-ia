"""Perfiles de refrigeración y curvas de PWM (funciones puras, testeables).

Perfiles de usuario:
- silent   : invierno / mínimo ruido.
- balanced : uso diario.
- max      : verano / máxima refrigeración.
- auto     : curva continua según la temperatura máxima.

El perfil ``custom`` se gestiona en el servicio a partir de ajustes manuales.
"""

from __future__ import annotations

from typing import Literal

ProfileName = Literal["silent", "balanced", "max", "auto", "custom"]

SELECTABLE_PROFILES = ("silent", "balanced", "max", "auto")
DEFAULT_PROFILE = "balanced"

# Objetivo fijo por perfil (porcentaje PWM).
PROFILE_TARGETS: dict[str, float] = {
    "silent": 30.0,
    "balanced": 50.0,
    "max": 100.0,
}

PROFILE_INFO: list[dict[str, object]] = [
    {
        "id": "silent",
        "label": "Silencioso",
        "description": "Invierno · mínimo ruido",
        "target_pwm_pct": 30,
    },
    {
        "id": "balanced",
        "label": "Equilibrado",
        "description": "Uso diario · temperatura y ruido",
        "target_pwm_pct": 50,
    },
    {
        "id": "max",
        "label": "Máximo",
        "description": "Verano · refrigeración máxima",
        "target_pwm_pct": 100,
    },
    {
        "id": "auto",
        "label": "Automático",
        "description": "Curva según la temperatura",
        "target_pwm_pct": None,
    },
]

# Puntos (temperatura °C, PWM %) de la curva automática. Interpolación lineal.
AUTO_CURVE: tuple[tuple[float, float], ...] = (
    (40.0, 25.0),
    (50.0, 32.0),
    (60.0, 45.0),
    (70.0, 65.0),
    (80.0, 85.0),
    (88.0, 100.0),
)


def clamp_pwm(value: float, min_pwm: float = 20.0) -> int:
    """Limita un PWM al rango seguro [min_pwm, 100] (redondeo half-up)."""
    bounded = max(min_pwm, min(100.0, float(value)))
    return int(bounded + 0.5)


def auto_target(max_temp_c: float | None, min_pwm: float = 20.0) -> int:
    """PWM de la curva automática para la temperatura máxima actual."""
    if max_temp_c is None:
        return clamp_pwm(40.0, min_pwm)
    if max_temp_c <= AUTO_CURVE[0][0]:
        return clamp_pwm(AUTO_CURVE[0][1], min_pwm)
    for (t0, p0), (t1, p1) in zip(AUTO_CURVE, AUTO_CURVE[1:]):
        if max_temp_c <= t1:
            ratio = (max_temp_c - t0) / (t1 - t0)
            return clamp_pwm(p0 + (p1 - p0) * ratio, min_pwm)
    return clamp_pwm(100.0, min_pwm)


def target_for_profile(
    profile: str, max_temp_c: float | None, min_pwm: float = 20.0
) -> int:
    """PWM objetivo para un perfil seleccionable."""
    if profile == "auto":
        return auto_target(max_temp_c, min_pwm)
    return clamp_pwm(PROFILE_TARGETS.get(profile, PROFILE_TARGETS["balanced"]), min_pwm)
