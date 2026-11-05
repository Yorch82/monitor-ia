"""Settings runtime: validación, clamping, máscara de API key y persist roundtrip."""

from app.core.settings import AlertThresholds, RuntimeSettings


def _base() -> RuntimeSettings:
    return RuntimeSettings(
        simulation_mode=True,
        refresh_interval_s=1.0,
        price_per_kwh=0.15,
        inference_base_url="http://host:11434/v1",
        inference_metrics_url="",
        inference_api_key="sk-test",
        inference_model="m",
        context_window=8192,
        token_source="auto",
        gpu_provider="auto",
        webhook_url="",
        history_retention_hours=24,
        thresholds=AlertThresholds(),
    )


def test_update_parcial():
    new = _base().apply_update({"price_per_kwh": 0.22, "refresh_interval_ms": 2000})
    assert new.price_per_kwh == 0.22
    assert new.refresh_interval_s == 2.0
    assert new.context_window == 8192  # sin tocar
    assert new is not _base()  # inmutable


def test_clamping():
    new = _base().apply_update(
        {
            "refresh_interval_ms": 10,     # mínimo 250
            "price_per_kwh": 999,          # máximo 100
            "context_window": 1,           # mínimo 256
            "thresholds": {"context_pct": 10, "gpu_temp_c": 500},
        }
    )
    assert new.refresh_interval_s == 0.25
    assert new.price_per_kwh == 100.0
    assert new.context_window == 256
    assert new.thresholds.context_pct == 50
    assert new.thresholds.gpu_temp_c == 110


def test_api_key_sesgurada_en_public_dict():
    pub = _base().to_public_dict()
    assert "inference_api_key" not in pub
    assert pub["inference_api_key_set"] is True


def test_roundtrip_persist():
    persisted = _base().to_persisted_dict()
    restored = _base().apply_update(persisted)
    assert restored == _base()
