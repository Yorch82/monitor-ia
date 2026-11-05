"""Ocupación de contexto: porcentaje, niveles de color y comportamiento edge-case."""

import pytest

from app.core.calculations import context_level, context_percent
from app.core.tokens import TokenAggregator
from app.core.models import RequestUsage, build_context


class TestContextPercent:
    def test_basico(self):
        assert context_percent(4096, 8192) == 50.0
        assert context_percent(8192, 8192) == 100.0

    def test_sin_datos_devuelve_none(self):
        assert context_percent(None, 8192) is None
        assert context_percent(100, None) is None
        assert context_percent(100, 0) is None

    def test_excede_ventana(self):
        # Sobre-el-100% se mantiene numérico (para alertas); las barras lo recortan.
        assert context_percent(9193, 8192) == 112.22


class TestContextLevel:
    def test_bordes_70_y_90(self):
        assert context_level(69.9) == "ok"
        assert context_level(70) == "warning"
        assert context_level(90) == "warning"
        assert context_level(90.1) == "critical"

    def test_nulos(self):
        assert context_level(None) == "none"


class TestAggregatorContext:
    def test_contexto_desde_usage_de_peticion(self):
        agg = TokenAggregator("proxy")
        agg.record_request(
            RequestUsage(ts=1000.0, input_tokens=1200, output_tokens=300, duration_s=2.0, model="demo"),
            count_tokens=True,
        )
        snap = agg.snapshot(now=1001.0, context_max=8192)
        assert snap.context.available is True
        assert snap.context.used_tokens == 1500
        assert snap.context.max_tokens == 8192
        assert snap.context.percent == round(1500 / 8192 * 100, 2)
        assert snap.context.level == "ok"

    def test_sin_max_no_hay_porcentaje(self):
        agg = TokenAggregator("proxy")
        agg.set_context(used=100, source="proxy", ts=1000.0)
        snap = agg.snapshot(now=1001.0, context_max=None)
        assert snap.context.available is False
        assert snap.context.percent is None


class TestBuildContext:
    def test_nivel_por_rango(self):
        assert build_context(500, 8192, "proxy").level == "ok"
        assert build_context(7000, 8192, "proxy").level == "warning"   # 85 %
        assert build_context(7900, 8192, "proxy").level == "critical"  # 96 %

    def test_sin_datos(self):
        ctx = build_context(None, 8192, "none")
        assert ctx.available is False
        ctx = build_context(100, 0, "none")
        assert ctx.available is False


@pytest.mark.parametrize(
    "used,max_tokens,expected_level",
    [(1000, 8192, "ok"), (6000, 8192, "warning"), (8000, 8192, "critical")],
)
def test_parametrizado(used: int, max_tokens: int, expected_level: str):
    assert build_context(used, max_tokens, "proxy").level == expected_level
