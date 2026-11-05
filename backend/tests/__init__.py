"""Tests del backend: cálculos puros (coste/contexto), alertas y settings.

Se ejecutan con:  cd backend && python -m pytest
"""

from app.core.calculations import (  # noqa: F401
    context_level,
    context_percent,
    cost_per_1k_tokens,
    cost_per_hour,
    energy_wh,
    projected_costs,
    session_cost_eur,
)
from app.core.settings import AlertThresholds
