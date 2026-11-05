"""Motor de alertas: umbrales, severidad y umbral de coste diario."""

import time

from app.core.alerts import AlertManager, AlertValues
from app.core.settings import AlertThresholds
from app.core.models import GpuReading

TH = AlertThresholds(context_pct=90, gpu_temp_c=80, vram_pct=95, ram_pct=90, daily_cost_eur=1.0)
NOW = 1_700_000_000.0


def _values(context=50.0, ram=None, gpus=None, daily_cost=0.0) -> AlertValues:
    return AlertValues(
        context_pct=context, ram_pct=ram, daily_cost=daily_cost, gpus=gpus or []
    )


def test_sin_alertas_bajo_umbrales():
    active, notify = AlertManager().evaluate(_values(), TH, NOW)
    assert active == []
    assert notify == []


def test_alerta_contexto():
    active, notify = AlertManager().evaluate(_values(context=91.0), TH, NOW)
    assert [a.id for a in active] == ["context"]
    assert active[0].severity == "warning"
    assert notify == active  # nueva → se notifica


def test_alerta_contexto_critico():
    active, _ = AlertManager().evaluate(_values(context=96.0), TH, NOW)
    assert active[0].severity == "critical"


def test_alertas_gpu_temp_y_vram():
    gpus = [
        GpuReading(index=0, name="RTX 4090", temperature_c=86.0, memory_used_mb=23_500, memory_total_mb=24_576),
    ]
    active, notify = AlertManager().evaluate(_values(gpus=gpus), TH, NOW)
    ids = sorted(a.id for a in active)
    assert ids == ["gpu0_temp", "gpu0_vram"]
    by_id = {a.id: a for a in active}
    assert by_id["gpu0_temp"].severity == "critical"  # 86 ≥ 80 · 1.075
    assert by_id["gpu0_vram"].severity == "warning"   # 95.6 % ≥ 95 % pero < 99.75 %
    assert len(notify) == 2


def test_alerta_ram():
    active, _ = AlertManager().evaluate(_values(ram=95.0), TH, NOW)
    assert active[0].id == "ram"
    assert active[0].severity == "critical"  # 95 ≥ 90 · 1.05
    active2, _ = AlertManager().evaluate(_values(ram=92.0), TH, NOW + 1)
    assert active2[0].severity == "warning"


def test_alerta_coste_diario():
    active, _ = AlertManager().evaluate(_values(daily_cost=1.25), TH, NOW)
    assert active[0].id == "daily_cost"
    assert active[0].severity == "critical"  # 1.25 ≥ 1.0 · 1.2
    # solo por encima del umbral → warning
    active1, _ = AlertManager().evaluate(_values(daily_cost=1.10), TH, NOW + 1)
    assert active1[0].severity == "warning"
    # por debajo del límite no dispara
    active2, _ = AlertManager().evaluate(_values(daily_cost=0.99), TH, NOW + 2)
    assert all(a.id != "daily_cost" for a in active2)


def test_cooldown_evita_spam_de_webhook():
    mgr = AlertManager(cooldown_s=300)
    _, first = mgr.evaluate(_values(context=95.0), TH, NOW)
    assert len(first) == 1
    _, second = mgr.evaluate(_values(context=95.0), TH, NOW + 10)  # persiste
    assert second == []
    _, later = mgr.evaluate(_values(context=95.0), TH, NOW + 301)  # pasa cooldown
    assert len(later) == 1


def test_escalado_renotifica():
    mgr = AlertManager(cooldown_s=300)
    mgr.evaluate(_values(context=91.0), TH, NOW)
    _, escalated = mgr.evaluate(_values(context=99.0), TH, NOW + 5)
    assert len(escalated) == 1
    assert escalated[0].severity == "critical"
