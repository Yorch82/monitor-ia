"""Simulador de refrigeración para probar el panel sin hardware ni permisos.

Genera temperaturas coherentes con el PWM aplicado (más ventilación ⇒ menos
temperatura, con inercia térmica) y ventiladores con RPM realistas. El control
es siempre "escribible" en simulación, de modo que se puedan probar perfiles
y sliders desde la UI.
"""

from __future__ import annotations

import random
import time
from typing import Any


class CoolingSimulator:
    def __init__(self, min_pwm: float) -> None:
        self.min_pwm = min_pwm
        self.cpu_temp = 48.0
        self.gpu_temp = 44.0
        self.vrm_temp = 40.0
        self.nvme_temp = 39.0
        self.load = 0.55  # carga sintética de la "IA"
        self._last_step = time.time()

        self._system_fans: dict[str, dict[str, Any]] = {
            "sim-cpu-fan": {"label": "CPU Fan", "pwm": 50.0},
            "sim-front-1": {"label": "Frontal 1", "pwm": 45.0},
            "sim-front-2": {"label": "Frontal 2", "pwm": 45.0},
            "sim-rear": {"label": "Trasero", "pwm": 50.0},
        }
        self._gpu_fan = {"label": "GPU 0 · Ventilador 1", "pwm": 45.0}

    def step(self, profile_target: int | None = None) -> None:
        now = time.time()
        dt = max(0.5, min(10.0, now - self._last_step))
        self._last_step = now

        avg_system = sum(f["pwm"] for f in self._system_fans.values()) / len(self._system_fans)
        avg_gpu = self._gpu_fan["pwm"]
        # Carga oscilante (simula ráfagas de inferencia).
        self.load += (random.uniform(0.25, 0.95) - self.load) * 0.15
        noise = random.uniform(-0.6, 0.6)

        cpu_target = 34.0 + 40.0 * (1.0 - avg_system / 100.0) + 8.0 * self.load + noise
        gpu_target = 32.0 + 44.0 * (1.0 - avg_gpu / 100.0) + 6.0 * self.load + noise
        vrm_target = 32.0 + 28.0 * (1.0 - avg_system / 100.0) + 4.0 * self.load
        nvme_target = 33.0 + 16.0 * (1.0 - avg_system / 100.0)

        alpha = 1.0 - pow(0.5, dt / 18.0)
        self.cpu_temp += (cpu_target - self.cpu_temp) * alpha
        self.gpu_temp += (gpu_target - self.gpu_temp) * alpha
        self.vrm_temp += (vrm_target - self.vrm_temp) * alpha
        self.nvme_temp += (nvme_target - self.nvme_temp) * alpha

    def set_pwm(self, fan_id: str, pwm_pct: int) -> None:
        if fan_id in self._system_fans:
            self._system_fans[fan_id]["pwm"] = float(pwm_pct)
        elif fan_id == "sim-gpu-fan-0":
            self._gpu_fan["pwm"] = float(pwm_pct)

    def set_all(self, pwm_pct: int) -> None:
        for fan in self._system_fans.values():
            fan["pwm"] = float(pwm_pct)

    def set_gpu(self, pwm_pct: int) -> None:
        self._gpu_fan["pwm"] = float(pwm_pct)

    def temperatures(self) -> list[dict[str, Any]]:
        return [
            {"id": "sim-cpu-package", "label": "CPU Package", "source": "cpu", "value_c": round(self.cpu_temp, 1), "chip": "sim"},
            {"id": "sim-cpu-core0", "label": "CPU Core 0", "source": "cpu", "value_c": round(self.cpu_temp - 4.0, 1), "chip": "sim"},
            {"id": "sim-gpu-temp", "label": "GPU 0 · RTX 4090 (sim)", "source": "gpu", "value_c": round(self.gpu_temp, 1), "chip": "sim"},
            {"id": "sim-vrm", "label": "VRM Motherboard", "source": "system", "value_c": round(self.vrm_temp, 1), "chip": "sim"},
            {"id": "sim-nvme", "label": "NVMe Composite", "source": "storage", "value_c": round(self.nvme_temp, 1), "chip": "sim"},
        ]

    def fans(self) -> list[dict[str, Any]]:
        result = []
        for fan_id, fan in self._system_fans.items():
            pwm = int(round(fan["pwm"]))
            result.append(
                {
                    "id": fan_id,
                    "label": fan["label"],
                    "kind": "system",
                    "source": "simulation",
                    "rpm": int(round(320 + pwm * 11 + random.uniform(-25, 25))),
                    "pwm_pct": pwm,
                    "controllable": True,
                    "min_pwm_pct": self.min_pwm,
                    "last_error": None,
                }
            )
        gpu_pwm = int(round(self._gpu_fan["pwm"]))
        result.append(
            {
                "id": "sim-gpu-fan-0",
                "label": self._gpu_fan["label"],
                "kind": "gpu",
                "source": "simulation",
                "rpm": int(round(280 + gpu_pwm * 14 + random.uniform(-30, 30))),
                "pwm_pct": gpu_pwm,
                "controllable": True,
                "min_pwm_pct": self.min_pwm,
                "last_error": None,
            }
        )
        return result
