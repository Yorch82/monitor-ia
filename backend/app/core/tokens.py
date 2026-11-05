"""Agregadores de tokens por fuente (proxy OpenAI-compatible, métricas Prometheus, simulación).

Cada ``TokenAggregator`` mantiene:
- totales acumulados de la sesión (input / output / nº peticiones),
- velocidad instantánea (ventana de 5 s) y media móvil de salida (ventana de 60 s),
- la última petición y un histórico reciente (para la UI),
- la ocupación de contexto observada (desde el ``usage`` de las peticiones).

El bucle de muestreo elige *una* aggregator activa según ``token_source`` y la serializa
en el ``TelemetryFrame``; las que no están activas siguen acumulando en segundo plano.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from typing import Literal

from app.core.models import ContextState, RequestUsage, TokensSnapshot

_WINDOW_INSTANT_S = 5.0
_WINDOW_MA_S = 60.0
_RECENT_MAX = 20
_PROXY_FRESH_S = 600.0  # ventana para considerar el proxy como fuente activa en modo auto


class _RateWindow:
    """Suma de tokens en una ventana temporal → tokens/s (media ponderada real)."""

    __slots__ = ("window_s", "_events")

    def __init__(self, window_s: float) -> None:
        self.window_s = window_s
        self._events: deque[tuple[float, float]] = deque()

    def record(self, ts: float, tokens: float) -> None:
        if tokens == 0:
            return
        self._events.append((ts, tokens))
        cutoff = ts - self.window_s
        while self._events and self._events[0][0] < cutoff:
            self._events.popleft()

    def rate(self, now: float) -> float:
        """Tokens por segundo en la ventana. El span real (mín. 1 s) evita inflar el valor al arrancar."""
        cutoff = now - self.window_s
        while self._events and self._events[0][0] < cutoff:
            self._events.popleft()
        if not self._events:
            return 0.0
        total = sum(t for _, t in self._events)
        span = min(self.window_s, max(1.0, now - self._events[0][0]))
        return total / span


class TokenAggregator:
    """Acumula tokens/rate/contexto de una única fuente de datos."""

    def __init__(self, name: Literal["proxy", "prometheus", "simulation"]) -> None:
        self.name = name
        self._input_tokens = 0
        self._output_tokens = 0
        self._requests = 0
        self._rate_instant_in = _RateWindow(_WINDOW_INSTANT_S)
        self._rate_instant_out = _RateWindow(_WINDOW_INSTANT_S)
        self._rate_ma_out = _RateWindow(_WINDOW_MA_S)
        self._last_request: RequestUsage | None = None
        self._recent: deque[RequestUsage] = deque(maxlen=_RECENT_MAX)
        self._ctx_used: int | None = None
        self._ctx_ts: float | None = None
        self._ctx_source: str = "none"

    # ── escritura ────────────────────────────────────────────────────────────

    def record_tick(
        self,
        ts: float,
        input_delta: int = 0,
        output_delta: int = 0,
        dt_s: float = 1.0,
    ) -> None:
        """Añade deltas de tokens producidos durante un tick (Prometheus/simulación)."""
        self._input_tokens += max(0, input_delta)
        self._output_tokens += max(0, output_delta)
        self._rate_instant_in.record(ts, max(0, input_delta))
        self._rate_instant_out.record(ts, max(0, output_delta))
        self._rate_ma_out.record(ts, max(0, output_delta))

    def record_request(self, usage: RequestUsage, *, count_tokens: bool = True) -> None:
        """Registra una petición completada (vía proxy). ``count_tokens=False`` evita
        el doble conteo cuando las métricas Prometheus son la fuente autoritativa;
        aun así se actualiza last-request y contexto."""
        if count_tokens:
            self._input_tokens += usage.input_tokens
            self._output_tokens += usage.output_tokens
        self._requests += 1
        self._last_request = usage
        self._recent.append(usage)
        if count_tokens:
            self._rate_instant_in.record(usage.ts, usage.input_tokens)
            self._rate_instant_out.record(usage.ts, usage.output_tokens)
            self._rate_ma_out.record(usage.ts, usage.output_tokens)
        self.set_context(
            used=usage.total_tokens, source="proxy", ts=usage.ts
        )

    def set_context(self, used: int | None, source: str, ts: float | None = None) -> None:
        """Actualiza la ocupación de contexto observada."""
        self._ctx_used = used
        self._ctx_ts = ts if ts is not None else time.time()
        self._ctx_source = source

    def reset_session(self) -> None:
        """Reinicia contadores de sesión (botón "Reiniciar sesión")."""
        self._input_tokens = 0
        self._output_tokens = 0
        self._requests = 0
        self._last_request = None
        self._recent.clear()
        self._rate_instant_in = _RateWindow(_WINDOW_INSTANT_S)
        self._rate_instant_out = _RateWindow(_WINDOW_INSTANT_S)
        self._rate_ma_out = _RateWindow(_WINDOW_MA_S)

    # ── consulta ─────────────────────────────────────────────────────────────

    def has_data(self) -> bool:
        return self._requests > 0 or self._input_tokens > 0 or self._output_tokens > 0

    def proxy_is_fresh(self, now: float) -> bool:
        """True si hubo tráfico vía proxy recientemente (para el modo auto)."""
        return self._ctx_ts is not None and (now - self._ctx_ts) <= _PROXY_FRESH_S

    def context_used(self) -> int | None:
        return self._ctx_used

    def context_source(self) -> str:
        return self._ctx_source

    def snapshot(self, now: float, context_max: int | None = None) -> TokensSnapshot:
        """Construye el snapshot completo para el frame, resolviendo el contexto con
        ``context_max`` (detectado por el monitor o configurado)."""
        ctx = ContextState(
            available=(self._ctx_used is not None and context_max is not None and context_max > 0),
            used_tokens=self._ctx_used,
            max_tokens=context_max if context_max else None,
            percent=(
                round(min(1000.0, self._ctx_used / context_max * 100.0), 2)
                if self._ctx_used is not None and context_max and context_max > 0
                else None
            ),
            level="none",
            source=self._ctx_source if self._ctx_used is not None else "none",
        )
        if ctx.percent is not None:
            ctx.level = _context_level(ctx.percent)
        return TokensSnapshot(
            source=self.name if self.has_data() else "none",
            input_tokens=self._input_tokens,
            output_tokens=self._output_tokens,
            total_tokens=self._input_tokens + self._output_tokens,
            requests=self._requests,
            instant_input_per_s=round(self._rate_instant_in.rate(now), 2),
            instant_output_per_s=round(self._rate_instant_out.rate(now), 2),
            moving_avg_output_per_s=round(self._rate_ma_out.rate(now), 2),
            last_request=self._last_request,
            recent_requests=list(self._recent),
            context=ctx,
        )


def _context_level(pct: float) -> Literal["ok", "warning", "critical"]:
    if pct > 90:
        return "critical"
    if pct >= 70:
        return "warning"
    return "ok"
