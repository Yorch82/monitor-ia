"""Ventiladores de GPU vía NVML (lectura siempre; escritura opt-in).

La escritura de ventiladores de GPU es delicada y no está soportada por todas
las tarjetas/drivers. Se activa con ``COOLING_GPU_FANS_ENABLED=true`` y
``COOLING_CONTROL_ENABLED=true``. Cualquier fallo se reporta sin romper el panel.
"""

from __future__ import annotations

import logging
from typing import Any

from app.cooling.hwmon import FanChannel

log = logging.getLogger(__name__)

try:
    import pynvml as _nvml  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover
    _nvml = None  # type: ignore[assignment]


class GpuFanController:
    """Lee temperaturas y controla los ventiladores de todas las GPUs NVIDIA."""

    def __init__(self, control_enabled: bool, gpu_fans_enabled: bool, min_pwm: float) -> None:
        self.control_enabled = control_enabled
        self.gpu_fans_enabled = gpu_fans_enabled
        self.min_pwm = min_pwm
        self.available = False
        self.error: str | None = None
        self._handles: list[Any] = []
        self._fan_counts: list[int] = []
        self._fan_map: dict[str, tuple[Any, int]] = {}
        self._fan_errors: dict[str, str] = {}
        self._init(control_enabled, gpu_fans_enabled)

    def _init(self, control_enabled: bool, gpu_fans_enabled: bool) -> None:
        if _nvml is None:
            self.error = "pynvml no instalado"
            return
        try:
            _nvml.nvmlInit()
            count = int(_nvml.nvmlDeviceGetCount())
            if count <= 0:
                self.error = "Sin GPUs NVIDIA visibles"
                return
            self._handles = [_nvml.nvmlDeviceGetHandleByIndex(i) for i in range(count)]
            self._fan_counts = [self._fan_count(handle) for handle in self._handles]
            self.available = True
            self.control_enabled = control_enabled
            self.gpu_fans_enabled = gpu_fans_enabled
        except Exception as exc:  # noqa: BLE001
            self.error = f"NVML: {exc}"

    def _fan_count(self, handle: Any) -> int:
        try:
            return max(1, int(_nvml.nvmlDeviceGetNumFans(handle)))
        except Exception:  # noqa: BLE001
            return 1

    def scan(self) -> dict[str, Any]:
        """Devuelve temperaturas y ventiladores GPU en formato snapshot."""
        temperatures: list[dict[str, Any]] = []
        fans: list[dict[str, Any]] = []
        writable = False
        self._fan_map = {}
        if not self.available or _nvml is None:
            return {"temperatures": temperatures, "fans": fans, "writable": False}

        for gpu_index, handle in enumerate(self._handles):
            name = f"GPU {gpu_index}"
            try:
                raw_name = _nvml.nvmlDeviceGetName(handle)
                if isinstance(raw_name, bytes):
                    raw_name = raw_name.decode(errors="replace")
                name = str(raw_name)
            except Exception:  # noqa: BLE001
                pass

            try:
                temp = float(_nvml.nvmlDeviceGetTemperature(handle, _nvml.NVML_TEMPERATURE_GPU))
                temperatures.append(
                    {
                        "id": f"gpu-{gpu_index}-temp",
                        "label": f"{name} · GPU",
                        "source": "gpu",
                        "value_c": round(temp, 1),
                        "chip": "nvidia",
                    }
                )
            except Exception:  # noqa: BLE001
                pass

            for fan_index in range(self._fan_counts[gpu_index]):
                fan_id = f"gpu-{gpu_index}-fan-{fan_index}"
                pct = self._read_fan_pct(handle, fan_index)
                rpm = self._read_fan_rpm(handle, fan_index)
                controllable = bool(
                    self.control_enabled and self.gpu_fans_enabled and pct is not None
                    and hasattr(_nvml, "nvmlDeviceSetFanSpeed_v2")
                )
                self._fan_map[fan_id] = (handle, fan_index)
                channel = FanChannel(
                    id=fan_id,
                    label=f"{name} · Ventilador {fan_index + 1}",
                    kind="gpu",
                    source="nvidia",
                    rpm=rpm,
                    pwm_pct=pct,
                    controllable=controllable,
                    min_pwm_pct=self.min_pwm,
                    last_error=self._fan_errors.get(fan_id),
                )
                fans.append(channel.to_dict())
                if controllable:
                    writable = True

        return {"temperatures": temperatures, "fans": fans, "writable": writable}

    def set_pwm(self, fan_id: str, pwm_pct: int) -> str | None:
        if not self.available or _nvml is None:
            return "GPU no disponible"
        if not (self.control_enabled and self.gpu_fans_enabled):
            return "Control de ventiladores de GPU desactivado"
        target = self._fan_map.get(fan_id)
        if target is None:
            return "Ventilador GPU no encontrado"
        handle, fan_index = target
        setter = getattr(_nvml, "nvmlDeviceSetFanSpeed_v2", None)
        if setter is None:
            return "Este driver no permite controlar el ventilador de la GPU"
        try:
            setter(handle, fan_index, int(pwm_pct))
            self._fan_errors.pop(fan_id, None)
            return None
        except Exception as exc:  # noqa: BLE001
            self._fan_errors[fan_id] = str(exc)
            log.warning("No se pudo ajustar ventilador GPU %s: %s", fan_id, exc)
            return str(exc)

    def restore_all(self) -> None:
        if not self.available or _nvml is None:
            return
        setter = getattr(_nvml, "nvmlDeviceSetDefaultFanSpeed_v2", None)
        if setter is None:
            return
        for fan_id, (handle, fan_index) in self._fan_map.items():
            try:
                setter(handle, fan_index)
                self._fan_errors.pop(fan_id, None)
            except Exception as exc:  # noqa: BLE001
                log.warning("No se pudo restaurar ventilador GPU %s: %s", fan_id, exc)

    def _read_fan_pct(self, handle: Any, fan_index: int) -> int | None:
        if _nvml is None:
            return None
        try:
            if hasattr(_nvml, "nvmlDeviceGetFanSpeed_v2"):
                return int(_nvml.nvmlDeviceGetFanSpeed_v2(handle, fan_index))
        except Exception:  # noqa: BLE001
            pass
        try:
            if fan_index == 0:
                return int(_nvml.nvmlDeviceGetFanSpeed(handle))
        except Exception:  # noqa: BLE001
            pass
        return None

    def _read_fan_rpm(self, handle: Any, fan_index: int) -> int | None:
        if _nvml is None:
            return None
        getter = getattr(_nvml, "nvmlDeviceGetFanSpeedRPM", None)
        if getter is None:
            return None
        try:
            return int(getter(handle, fan_index))
        except Exception:  # noqa: BLE001
            return None
