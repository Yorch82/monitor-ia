"""Motor de simulación: genera datos sintéticos realistas sin hardware ni modelo.

Simula una carga de inferencia con máquina de estados (idle → prompt → generate),
y deriva GPU/temperatura/ventilador/potencia/tokens de forma coherente con inercia
térmica y ruido, de modo que las gráficas parezcan telemetría real.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from typing import Any

from app.config import AppConfig
from app.core.models import GpuReading, RequestUsage


@dataclass
class _GpuState:
    """Estado térmico/energético de una GPU virtual."""

    index: int
    base_vram_mb: float
    util: float = 5.0
    temp_c: float = 36.0
    fan_pct: float = 15.0
    vram_used_mb: float = 0.0
    power_w: float = 20.0

    def step(self, ts: float, target_util: float, dt: float, config: AppConfig, busy_vram: float) -> None:
        # Utilización: suavizado exponencial hacia el objetivo con ruido.
        alpha = 1.0 - pow(0.001, dt / 2.0)  # constante de tiempo ≈ 2 s
        self.util += (target_util - self.util) * alpha
        self.util = max(0.0, min(100.0, self.util + random.uniform(-2.5, 2.5)))

        # Térmicas: objetivo depende de utilización; inercia ≈ 25 s, ventilador ≈ 8 s.
        temp_target = 33.0 + self.util * 0.46 + random.uniform(-0.6, 0.6)
        self.temp_c += (temp_target - self.temp_c) * (1.0 - pow(0.001, dt / 25.0))
        self.temp_c = max(28.0, min(92.0, self.temp_c))
        fan_target = max(12.0, min(100.0, (self.temp_c - 30.0) * 2.1))
        self.fan_pct += (fan_target - self.fan_pct) * (1.0 - pow(0.001, dt / 8.0))

        # Potencia: curva sobre el TDP simulado (idle ≈ 10 %, carga ≈ 90 %).
        fraction = 0.10 + 0.80 * (self.util / 100.0) ** 1.2
        self.power_w += (
            config.sim_power_limit_w * fraction + random.uniform(-6, 6) - self.power_w
        ) * alpha

        # VRAM: modelo residente + crecimiento suave mientras genera.
        target_vram = self.base_vram_mb + busy_vram
        self.vram_used_mb += (target_vram - self.vram_used_mb) * (1.0 - pow(0.001, dt / 3.0))

    def reading(self, config: AppConfig) -> GpuReading:
        label = "NVIDIA GeForce RTX 4090" if config.sim_gpu_count == 1 else f"NVIDIA GeForce RTX 4090 (GPU {self.index})"
        return GpuReading(
            index=self.index,
            name=f"{label} · simulada",
            vendor="nvidia",
            utilization_pct=round(self.util, 1),
            memory_used_mb=round(self.vram_used_mb, 1),
            memory_total_mb=round(config.sim_vram_total_mb, 1),
            temperature_c=round(self.temp_c, 1),
            fan_pct=round(self.fan_pct, 1),
            power_w=round(self.power_w, 1),
            power_limit_w=config.sim_power_limit_w,
        )


@dataclass
class SimResult:
    """Salida de un step del simulador."""

    ts: float = 0.0
    gpus: list[GpuReading] = field(default_factory=list)
    input_delta: int = 0
    output_delta: int = 0
    completed: RequestUsage | None = None
    context_used: int = 0
    cpu_pct: float = 8.0
    ram_used_gb: float = 20.0
    ram_total_gb: float = 64.0
    latency_ms: float = 40.0


class Simulator:
    """Máquina de estados de carga sintética (idle → prompt → generate → idle…)."""

    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._gpus = [
            _GpuState(index=i, base_vram_mb=random.uniform(6_500, 9_800))
            for i in range(max(1, config.sim_gpu_count))
        ]
        self.reset()

    # ── control de sesión ────────────────────────────────────────────────────

    def reset(self) -> None:
        """Reinicia contadores y máquina de estados (botón Reiniciar sesión)."""
        now = time.time()
        self._phase = "idle"
        self._next_ts = now + random.uniform(0.8, 2.5)
        self._prompt_target = 0
        self._prompt_done = 0.0
        self._gen_target = 0
        self._gen_done = 0.0
        self._gen_tps = 0.0
        self._req_start = 0.0
        self._req_input = 0
        self._req_output = 0
        self._context_used = random.randint(400, 1200)
        self._cpu = 12.0
        self._ram_used = self._config.sim_ram_total_gb * random.uniform(0.28, 0.36)
        self._last_step = now

    # ── bucle principal ──────────────────────────────────────────────────────

    def step(self, settings) -> SimResult:
        """Avanza la simulación por un tick (≈ intervalo de muestreo) y devuelve el frame.

        ``settings`` es el ``RuntimeSettings`` vivo (context_window, inference_model…).
        """
        now = time.time()
        dt = max(0.05, min(30.0, now - self._last_step))
        self._last_step = now

        input_delta = 0
        output_delta = 0
        completed: RequestUsage | None = None
        remaining = dt

        # Avanza la máquina de estados dentro del tick (puede haber transiciones).
        guard = 0
        while remaining > 1e-3 and guard < 16:
            guard += 1
            if self._phase == "idle":
                if now >= self._next_ts:
                    self._start_request(now)
                remaining = 0.0
                break

            rate = self._prompt_rate() if self._phase == "prompt" else self._gen_tps
            target = self._prompt_target if self._phase == "prompt" else self._gen_target
            done = self._prompt_done if self._phase == "prompt" else self._gen_done
            pending = max(0.0, target - done)
            elapsed = remaining * rate
            portion = min(elapsed, pending)
            if self._phase == "prompt":
                self._prompt_done += portion
                self._req_input = int(self._prompt_done)
                input_delta += int(portion)
                self._context_used += int(portion)
            else:
                self._gen_done += portion
                self._req_output = int(self._gen_done)
                output_delta += int(portion)
                self._context_used += int(portion)
            remaining -= portion / max(rate, 1e-6)

            if portion >= pending - 1e-6:
                # fase completada
                if self._phase == "prompt":
                    self._phase = "generate"
                    self._gen_target = int(random.uniform(120, 850))
                    self._gen_done = 0.0
                    self._gen_tps = random.uniform(28, 95)
                else:
                    completed = RequestUsage(
                        ts=now,
                        input_tokens=self._req_input,
                        output_tokens=self._req_output,
                        duration_s=max(0.05, now - self._req_start),
                        model=settings.inference_model,
                    )
                    self._phase = "idle"
                    self._next_ts = now + random.uniform(0.8, 4.0)

        # Reset de contexto cuando la ventana se llena (nueva conversación simulada).
        ctx_max = settings.context_window
        if self._context_used > ctx_max * 0.97:
            self._context_used = random.randint(350, 900)

        # ── hardware sintético coherente con la fase ─────────────────────────
        target_util = self._target_util()
        busy_vram = self._busy_vram_bytes()
        for g in self._gpus:
            g.step(now, target_util, dt, self._config, busy_vram)

        util_avg = sum(g.util for g in self._gpus) / len(self._gpus)
        cpu_target = 4.0 + util_avg * 0.5 + random.uniform(-3, 3)
        self._cpu += (cpu_target - self._cpu) * 0.35
        ram_target = self._config.sim_ram_total_gb * (0.30 + 0.10 * util_avg / 100.0) + random.uniform(-0.5, 0.5)
        self._ram_used += (ram_target - self._ram_used) * 0.15

        return SimResult(
            ts=now,
            gpus=[g.reading(self._config) for g in self._gpus],
            input_delta=input_delta,
            output_delta=output_delta,
            completed=completed,
            context_used=self._context_used,
            cpu_pct=round(max(1.0, self._cpu), 1),
            ram_used_gb=round(self._ram_used, 2),
            ram_total_gb=round(self._config.sim_ram_total_gb, 2),
            latency_ms=round(random.uniform(25, 70), 1),
        )

    # ── internals ────────────────────────────────────────────────────────────

    def _start_request(self, ts: float) -> None:
        self._phase = "prompt"
        self._req_start = ts
        self._req_input = 0
        self._req_output = 0
        self._prompt_target = int(random.uniform(150, 1800))
        self._prompt_done = 0.0

    def _prompt_rate(self) -> float:
        return max(800.0, self._prompt_target / max(0.08, random.uniform(0.1, 0.4)))

    def _target_util(self) -> float:
        if self._phase == "idle":
            return random.uniform(3, 9)
        if self._phase == "prompt":
            return random.uniform(94, 99)
        return random.uniform(88, 98)

    def _busy_vram_bytes(self) -> float:
        return 512.0 if self._phase != "idle" else 0.0
