"""Evaluación de alertas contra umbrales configurables + seguimiento de estado.

Es un módulo *puro* (sin I/O) para poder testearlo con pytest: ``AlertManager.evaluate``
devuelve las alertas activas y la lista de alertas "nuevas o re-escaladas" que el
sampler se encarga de notificar (toast visual + webhook opcional con cooldown).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.core.models import AlertItem, GpuReading
from app.core.settings import AlertThresholds

Severity = Literal["warning", "critical"]

WebhookCooldownS = 300.0  # anti-spam de webhook por alerta


def _severity(value: float, threshold: float, critical_mult: float = 1.05) -> Severity:
    """``critical`` cuando el valor supera holgadamente el umbral; ``warning`` si no."""
    return "critical" if value >= threshold * critical_mult else "warning"


@dataclass(frozen=True)
class AlertValues:
    """Valores crudos necesarios para evaluar los umbrales en un tick."""

    context_pct: float | None
    ram_pct: float | None
    daily_cost: float
    gpus: list[GpuReading]


class AlertManager:
    """Mantiene el estado de alertas activas y decide cuándo re-notificar."""

    def __init__(self, cooldown_s: float = WebhookCooldownS) -> None:
        self._state: dict[str, Severity] = {}
        self._last_sent: dict[str, float] = {}

    def evaluate(
        self, values: AlertValues, thresholds: AlertThresholds, now: float
    ) -> tuple[list[AlertItem], list[AlertItem]]:
        """Devuelve (alertas_activas, alertas_a_notificar).

        Una alerta se notifica cuando aparece o escala de severidad, o cuando su
        webhook supera el cooldown (recordatorio periódico mientras persista).
        """
        active: list[AlertItem] = []

        # ── contexto ─────────────────────────────────────────────────────────
        if values.context_pct is not None and values.context_pct > thresholds.context_pct:
            active.append(
                AlertItem(
                    id="context",
                    severity=_severity(values.context_pct, thresholds.context_pct, 1.06),
                    message=f"Contexto al {values.context_pct:.0f}% (límite {thresholds.context_pct:.0f}%)",
                    value=values.context_pct,
                    threshold=thresholds.context_pct,
                    ts=now,
                )
            )

        # ── GPU: temperatura y VRAM (por tarjeta) ────────────────────────────
        for g in values.gpus:
            label = g.name or f"GPU {g.index}"
            short = f"GPU {g.index}"
            if g.temperature_c is not None and g.temperature_c > thresholds.gpu_temp_c:
                active.append(
                    AlertItem(
                        id=f"gpu{g.index}_temp",
                        severity=_severity(g.temperature_c, thresholds.gpu_temp_c, 1.075),
                        message=f"{short}: {g.temperature_c:.0f} ºC (límite {thresholds.gpu_temp_c:.0f} ºC) — {label}",
                        value=g.temperature_c,
                        threshold=thresholds.gpu_temp_c,
                        ts=now,
                    )
                )
            mem_pct = g.memory_pct
            if mem_pct is not None and mem_pct > thresholds.vram_pct:
                active.append(
                    AlertItem(
                        id=f"gpu{g.index}_vram",
                        severity=_severity(mem_pct, thresholds.vram_pct),
                        message=f"{short}: VRAM al {mem_pct:.0f}% (límite {thresholds.vram_pct:.0f}%) — {label}",
                        value=mem_pct,
                        threshold=thresholds.vram_pct,
                        ts=now,
                    )
                )

        # ── RAM ──────────────────────────────────────────────────────────────
        if values.ram_pct is not None and values.ram_pct > thresholds.ram_pct:
            active.append(
                AlertItem(
                    id="ram",
                    severity=_severity(values.ram_pct, thresholds.ram_pct),
                    message=f"RAM al {values.ram_pct:.0f}% (límite {thresholds.ram_pct:.0f}%)",
                    value=values.ram_pct,
                    threshold=thresholds.ram_pct,
                    ts=now,
                )
            )

        # ── coste diario ─────────────────────────────────────────────────────
        if thresholds.daily_cost_eur > 0 and values.daily_cost > thresholds.daily_cost_eur:
            active.append(
                AlertItem(
                    id="daily_cost",
                    severity=_severity(values.daily_cost, thresholds.daily_cost_eur, 1.2),
                    message=f"Coste diario {values.daily_cost:.2f} € (límite {thresholds.daily_cost_eur:.2f} €)",
                    value=values.daily_cost,
                    threshold=thresholds.daily_cost_eur,
                    ts=now,
                )
            )

        # ── decide qué notificar ─────────────────────────────────────────────
        to_notify: list[AlertItem] = []
        new_state: dict[str, Severity] = {}
        for alert in active:
            prev = self._state.get(alert.id)
            new_state[alert.id] = alert.severity
            escalated = prev is not None and _SEV_RANK[alert.severity] > _SEV_RANK[prev]
            is_new = prev is None
            cooldown_ok = (now - self._last_sent.get(alert.id, 0.0)) >= self._cooldown_guard()
            if is_new or escalated or cooldown_ok:
                to_notify.append(alert)
                self._last_sent[alert.id] = now
        self._state = new_state
        return active, to_notify

    def _cooldown_guard(self) -> float:
        return self._cooldown

    def reset(self) -> None:
        self._state.clear()
        self._last_sent.clear()

    _cooldown = WebhookCooldownS


_SEV_RANK: dict[str, int] = {"warning": 1, "critical": 2}
