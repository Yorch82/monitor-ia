"""Persistencia: la energía diaria debe sumar deltas por muestra (no acumulados)."""

from pathlib import Path

from app.storage.database import HistoryStore


def _insert(store: HistoryStore, ts: float, energy_delta_wh: float) -> None:
    store.insert_sample(
        ts=ts,
        payload={"tokens": {}, "context": {}, "system": {}, "hardware": {}, "cost": {}, "gpus": []},
        input_total=0,
        output_total=0,
        moving_avg_tps=0.0,
        context_pct=None,
        gpu_pct=None,
        gpu_temp_c=None,
        vram_pct=None,
        power_w=400.0,
        energy_delta_wh=energy_delta_wh,
        ram_pct=10.0,
        cpu_pct=5.0,
        cost_per_hour=0.06,
    )


def test_energy_since_suma_deltas(tmp_path: Path):
    store = HistoryStore(tmp_path / "test.db")
    _insert(store, 1000.0, 1.5)
    _insert(store, 1001.0, 2.5)
    _insert(store, 1002.0, 0.5)
    assert store.energy_since(0) == 4.5
    assert store.energy_since(1001.5) == 0.5
    store.close()


def test_migracion_anade_columna_energia(tmp_path: Path):
    import sqlite3

    db = tmp_path / "legacy.db"
    conn = sqlite3.connect(db)
    conn.execute(
        """CREATE TABLE samples (
            id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL, input_total INTEGER,
            output_total INTEGER, moving_avg_tps REAL, context_pct REAL, gpu_pct REAL,
            gpu_temp_c REAL, vram_pct REAL, power_w REAL, energy_wh REAL, ram_pct REAL,
            cpu_pct REAL, cost_per_hour REAL, payload TEXT)"""
    )
    conn.commit()
    conn.close()

    store = HistoryStore(db)
    _insert(store, 2000.0, 3.0)
    assert store.energy_since(0) == 3.0
    store.close()
