"""Métricas del sistema (CPU, RAM, swap y uptime) con psutil."""

from __future__ import annotations

import logging
import time

import psutil

from app.core.models import SystemReading

log = logging.getLogger(__name__)


class SystemSampler:
    """Muestreo de sistema. ``cpu_percent`` necesita una primera llamada de cebado."""

    def __init__(self) -> None:
        try:
            psutil.cpu_percent(interval=None)  # cebado: la 1ª llamada devuelve 0/None
            self._boot = psutil.boot_time()
            self.available = True
        except Exception as exc:  # noqa: BLE001
            self.available = False
            self.error = str(exc)
            log.warning("SystemSampler no disponible: %s", exc)

    def sample(self) -> SystemReading:
        if not self.available:
            return SystemReading()
        try:
            vm = psutil.virtual_memory()
            swap = psutil.swap_memory()
            cpu = psutil.cpu_percent(interval=None)
            return SystemReading(
                cpu_pct=round(float(cpu), 1),
                cpu_count=psutil.cpu_count(logical=True),
                ram_used_gb=round(vm.used / 1024**3, 2),
                ram_total_gb=round(vm.total / 1024**3, 2),
                ram_pct=round(vm.percent, 1),
                swap_used_gb=round(swap.used / 1024**3, 2),
                swap_total_gb=round(swap.total / 1024**3, 2),
                swap_pct=round(swap.percent, 1),
                uptime_s=round(max(0.0, time.time() - self._boot), 0),
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("SystemSampler fallo: %s", exc)
            return SystemReading()
