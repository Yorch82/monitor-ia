"""Coste energético: energía integrada, coste sesión, proyecciones y coste/1k tokens."""

from app.core.calculations import (
    cost_per_1k_tokens,
    cost_per_hour,
    energy_wh,
    projected_costs,
    session_cost_eur,
    wh_to_kwh,
)


def test_energy_wh_basico():
    # 400 W durante 60 s = 6.67 Wh
    assert energy_wh(400, 60) == 400 * 60 / 3600


def test_energy_wh_sin_datos():
    assert energy_wh(None, 60) == 0
    assert energy_wh(400, 0) == 0
    assert energy_wh(400, -5) == 0


def test_wh_to_kwh():
    assert wh_to_kwh(1000) == 1
    assert wh_to_kwh(37) == 0.037


def test_session_cost():
    # 1 kWh a 0.25 €/kWh = 0.25 €
    assert session_cost_eur(1000, 0.25) == 0.25
    # 365 Wh (0.365 kWh) a 0.15 €/kWh = 0.0548 €
    assert session_cost_eur(365, 0.15) == 0.0548


def test_cost_per_hour_con_potencia_nula():
    assert cost_per_hour(None, 0.15) is None
    # 300 W = 0.3 kWh/h → 0.3 · 0.15 = 0.045 €/h
    assert cost_per_hour(300, 0.15) == 0.045


def test_proyeccion_dia_mes():
    cost_h = cost_per_hour(300, 0.15)  # 0.045 €/h
    day, month = projected_costs(cost_h)
    assert day == round(0.045 * 24, 2)
    assert month == round(0.045 * 24 * 30, 2)
    assert projected_costs(None) == (None, None)


def test_cost_per_1k_tokens():
    # 250 tokens generados, coste 0.10 € → 0.10 / 0.25 = 0.4 €/1k
    assert cost_per_1k_tokens(0.10, 250) == 0.4
    assert cost_per_1k_tokens(5.0, 0) is None
    assert cost_per_1k_tokens(0.0, 1000) is None


def test_costes_con_precio_intercambiable():
    assert session_cost_eur(2000, 0.30) == 0.60
