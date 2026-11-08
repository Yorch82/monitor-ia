"""Tests de perfiles y curva de refrigeración (seguridad PWM incluida)."""

import pytest

from app.cooling.profiles import auto_target, clamp_pwm, target_for_profile


def test_clamp_pwm_limites():
    assert clamp_pwm(0, 20) == 20
    assert clamp_pwm(15.4, 20) == 20
    assert clamp_pwm(45, 20) == 45
    assert clamp_pwm(100, 20) == 100
    assert clamp_pwm(150, 20) == 100


@pytest.mark.parametrize(
    "profile,expected",
    [("silent", 30), ("balanced", 50), ("max", 100)],
)
def test_perfiles_fijos(profile, expected):
    assert target_for_profile(profile, max_temp_c=70, min_pwm=20) == expected


def test_silent_respeta_minimo():
    assert target_for_profile("silent", 70, min_pwm=35) == 35
    assert target_for_profile("max", 99, min_pwm=35) == 100


def test_curva_automatica_puntos():
    assert auto_target(35, 20) == 25
    assert auto_target(40, 20) == 25
    assert auto_target(50, 20) == 32
    assert auto_target(60, 20) == 45
    assert auto_target(70, 20) == 65
    assert auto_target(80, 20) == 85
    assert auto_target(90, 20) == 100
    assert auto_target(None, 20) == 40


def test_curva_automatica_interpolacion():
    # Entre 50 °C (32 %) y 60 °C (45 %): 55 °C ≈ 38,5 %
    assert auto_target(55, 20) == 39
    # El mínimo global se aplica a la curva.
    assert auto_target(40, 50) == 50
