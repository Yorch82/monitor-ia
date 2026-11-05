"""Proveedor NVIDIA vía NVML (pynvml / nvidia-ml-py).

Soporta múltiples GPUs: devuelve una lectura ``GpuReading`` por tarjeta. Los campos
que NVML no reporte (p. ej. ventilador en portátiles) quedan en ``None``.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from app.core.models import GpuReading
from app.metrics.base import GpuProvider

log = logging.getLogger(__name__)

try:  # el paquete PyPI se llama "nvidia-ml-py" y el módulo "pynvml"
    import pynvml as _nvml  # type: ignore[import-untyped]
except ImportError:  # entorno sin la librería instalada
    _nvml = None  # type: ignore[assignment]


class NvidiaProvider(GpuProvider):
    name = "nvidia"

    def __init__(self) -> None:
        super().__init__()
        self._handles: list[Any] = []
        if _nvml is None:
            self.error = "El paquete 'nvidia-ml-py' no está instalado"
            return
        try:
            _nvml.nvmlInit()
            count = int(_nvml.nvmlDeviceGetCount())
            self._handles = [_nvml.nvmlDeviceGetHandleByIndex(i) for i in range(count)]
            self.available = count > 0
            if not self.available:
                self.error = "NVML inicializado pero sin GPUs visibles"
        except Exception as exc:  # noqa: BLE001
            self.error = _friendly_error(exc)
            self.available = False
            log.warning("NvidiaProvider: %s", self.error)

    def _sample_impl(self) -> list[GpuReading]:
        if not self.available or _nvml is None:
            return []
        readings: list[GpuReading] = []
        for index, handle in enumerate(self._handles):
            readings.append(self._read_gpu(index, handle))
        return readings

    def _read_gpu(self, index: int, handle: Any) -> GpuReading:
        def safe(label: str, fn: Callable[..., Any]) -> Any:
            try:
                return fn()
            except Exception:  # noqa: BLE001 — atributo no soportado por el driver
                log.debug("NVML '%s' no disponible en GPU %d", label, index)
                return None

        name = safe("name", lambda: _nvml.nvmlDeviceGetName(handle))
        name = name.decode() if isinstance(name, bytes) else (name or f"GPU {index}")

        mem = safe("memory", lambda: _nvml.nvmlDeviceGetMemoryInfo(handle))
        mem_total = None
        mem_used = None
        if mem is not None:
            mem_used = round(mem.total_used / 1024**2, 1)
            mem_total = round(mem.total / 1024**2, 1)

        util = safe("util", lambda: _nvml.nvmlDeviceGetUtilizationRates(handle))
        util_pct = round(util.gpu, 1) if util else None

        temp = safe("temp", lambda: _nvml.nvmlDeviceGetTemperature(handle, _nvml.NVML_TEMPERATURE_GPU))

        fan = None
        if (_nvml.nvmlDeviceGetNumFans(handle) if hasattr(_nvml, "nvmlDeviceGetNumFans") else 1) > 0:
            fan = safe("fan", lambda: _nvml.nvmlDeviceGetFanSpeed(handle, 0))

        # mW → W
        power_draw_mw = safe("power", lambda: _nvml.nvmlDeviceGetPowerUsage(handle))
        power_limit_mw = safe(
            "power_limit",
            lambda: _nvml.nvmlDeviceGetEnforcedPowerLimit(handle)
            or _nvml.nvmlDeviceGetPowerManagementLimit(handle),
        )

        return GpuReading(
            index=index,
            name=name,
            vendor="nvidia",
            utilization_pct=util_pct,
            memory_used_mb=mem_used,
            memory_total_mb=mem_total,
            temperature_c=float(temp) if temp is not None else None,
            fan_pct=float(fan) if fan is not None else None,
            power_w=round(power_draw_mw / 1000, 1) if power_draw_mw else None,
            power_limit_w=round(power_limit_mw / 1000, 1) if power_limit_mw else None,
        )


def _friendly_error(exc: Exception) -> str:
    text = str(exc)
    if "Driver Not Loaded" in text or "-6003" in text:
        return "Driver NVIDIA no disponible o sin GPU (¿contenedor sin acceso GPU?)"
    return f"NVML: {text}"
