"""Bucle de muestreo: construye el ``TelemetryFrame`` cada tick y lo difunde/persiste.

Cada tick:
1) muestra la fuente activa (simulación o proveedores reales + monitor de inferencia),
2) integra la energía (W · Δt), calcula costes, evalúa alertas,
3) persiste en SQLite, emite por WebSocket y restaura métricas obsoletas.
Nunca lanza: un fallo destruye el tick → frame degradado con "sin datos".
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import asdict

from app.core.alerts import AlertManager, AlertValues
from app.core.calculations import (
    cost_per_1k_tokens,
    cost_per_hour,
    energy_wh,
    projected_costs,
    session_cost_eur,
    start_of_day_ts,
)
from app.core.models import (
    CostSnapshot,
    HardwareStatus,
    InferenceStatus,
    PowerSnapshot,
    TelemetryFrame,
    TokensSnapshot,
    SystemReading,
    utc_iso,
)
from app.core.settings import RuntimeSettings, SettingsManager
from app.core.tokens import TokenAggregator
from app.inference.monitor import InferenceMonitor
from app.metrics.base import GpuProvider
from app.metrics.system import SystemSampler
from app.telemetry.simulator import Simulator
from app.storage.database import HistoryStore

log = logging.getLogger(__name__)

_ENERGY_DT_MAX_S = 10.0  # acota la integración si hubo pausas (hibernación, etc.)
_PRUNE_EVERY_TICKS = 600  # poda del histórico ≈ cada 10 min a 1 Hz


def _frame_json(frame: TelemetryFrame) -> str:
    """Serializa el frame para WebSocket/API."""
    import json

    return json.dumps(frame.to_dict(), ensure_ascii=False)


class TelemetrySampler:
    """Orquesta el muestreo completo. Se ejecuta como tarea async del lifespan."""

    def __init__(
        self,
        settings: SettingsManager,
        store: HistoryStore,
        provider: GpuProvider,
        monitor: InferenceMonitor,
        simulator: Simulator,
        aggregators: dict[str, TokenAggregator],
        system_sampler: SystemSampler,
        publish,          # async (payload_json: str) -> None coro del Hub
        webhook_client,   # httpx.AsyncClient para el webhook de alertas
    ) -> None:
        self.settings = settings
        self.store = store
        self.provider = provider
        self.monitor = monitor
        self.simulator = simulator
        self.aggregators = aggregators
        self.system_sampler = system_sampler
        self._publish = publish
        self._webhook_client = webhook_client

        self._alerts = AlertManager()
        self._started_ts = time.time()
        self._last_tick_ts: float | None = None
        self._energy_session_wh = 0.0
        self._last_stored_energy_wh = 0.0  # para guardar deltas de energía por muestra
        self._tick_count = 0
        self._latest_frame: TelemetryFrame | None = None
        self._task: asyncio.Task | None = None
        # Guardamos el "kind" configurado (auto|nvidia|…), no el name del proveedor
        # construido (que puede ser NoGpuProvider/none tras la auto-detección).
        self._provider_kind = settings.get().gpu_provider

    # ── ciclo de vida ────────────────────────────────────────────────────────

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name="telemetry-sampler")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    def latest(self) -> TelemetryFrame:
        """Último frame conocido (para GET /api/telemetry y reconexiones)."""
        return self._latest_frame or TelemetryFrame(ts=time.time(), ts_iso=utc_iso(time.time()))

    def uptime_s(self) -> float:
        return max(0.0, time.time() - self._started_ts)

    # ── bucle ────────────────────────────────────────────────────────────────

    async def _run(self) -> None:
        log.info("Sampler iniciado")
        while True:
            s = self.settings.get()
            started = time.perf_counter()
            try:
                frame = await self._collect()
            except Exception as exc:  # noqa: BLE001 — último recurso
                log.exception("Fallo construyendo frame: %s", exc)
                frame = self._degraded_frame(str(exc))
            try:
                await self._emit(frame)
            except Exception:  # noqa: BLE001
                log.exception("Fallo difundiendo frame")

            used = time.perf_counter() - started
            sleep = max(0.05, s.refresh_interval_s - used)
            await asyncio.sleep(sleep)

    # ── recolección ──────────────────────────────────────────────────────────

    async def _collect(self) -> TelemetryFrame:
        now = time.time()
        s = self.settings.get()
        dt = self._tick_dt(now)

        if s.simulation_mode:
            frame = await self._frame_simulation(now, dt, s)
        else:
            frame = await self._frame_live(now, dt, s)

        return self._finalize(frame, now, dt, s)

    def _tick_dt(self, now: float) -> float:
        if self._last_tick_ts is None:
            return 0.0
        return max(0.0, min(now - self._last_tick_ts, _ENERGY_DT_MAX_S * 3))

    async def _frame_simulation(self, now: float, dt: float, s: RuntimeSettings) -> TelemetryFrame:
        sim = self.simulator.step(s)  # avanza la máquina de estados sintética
        agg = self.aggregators["simulation"]
        agg.record_tick(ts=now, input_delta=sim.input_delta, output_delta=sim.output_delta, dt_s=max(0.1, dt))
        if sim.completed:
            agg.record_request(sim.completed, count_tokens=True)
        tokens = agg.snapshot(now, context_max=s.context_window)

        return TelemetryFrame(
            ts=now,
            ts_iso=utc_iso(now),
            mode="simulation",
            interval_s=s.refresh_interval_s,
            tokens=tokens,
            gpus=sim.gpus,
            hardware=HardwareStatus(gpu_available=bool(sim.gpus), provider="simulation", mode="simulation"),
            system=SystemReading(
                cpu_pct=sim.cpu_pct,
                cpu_count=8,
                ram_used_gb=sim.ram_used_gb,
                ram_total_gb=sim.ram_total_gb,
                ram_pct=round(sim.ram_used_gb / sim.ram_total_gb * 100, 1),
                swap_used_gb=0.0,
                swap_total_gb=0.0,
                swap_pct=0.0,
                uptime_s=self.uptime_s(),
            ),
            inference=InferenceStatus(
                status="online",
                engine="simulación",
                model=s.inference_model,
                latency_ms=sim.latency_ms,
                context_hint_tokens=s.context_window,
                context_hint_source="simulation",
            ),
        )

    async def _frame_live(self, now: float, dt: float, s: RuntimeSettings) -> TelemetryFrame:
        s_refresh = self.settings.get()
        gpus = await self.provider.sample()
        system = self.system_sampler.sample()
        inference_status = await self.monitor.poll(now)

        tokens = self._tokens_snapshot(now, s_refresh)
        err = self.provider.error if not self.provider.available and self.provider.error else None
        return TelemetryFrame(
            ts=now,
            ts_iso=utc_iso(now),
            mode="live",
            interval_s=s_refresh.refresh_interval_s,
            tokens=tokens,
            gpus=gpus,
            hardware=HardwareStatus(
                gpu_available=bool(gpus),
                gpu_error=err,
                provider=self.provider.name,
                mode="live",
            ),
            system=system,
            inference=inference_status,
        )

    def _tokens_snapshot(self, now: float, s: RuntimeSettings) -> TokensSnapshot:
        """Elige la aggregator activa según token_source y los datos disponibles."""
        proxy = self.aggregators["proxy"]
        prom = self.aggregators["prometheus"]

        if s.token_source == "proxy":
            active = proxy
        elif s.token_source == "prometheus":
            active = prom
        elif s.token_source == "none":
            active = None
        else:  # auto
            if self.monitor.prometheus_active:
                active = prom
            elif proxy.proxy_is_fresh(now):
                active = proxy
            else:
                active = None

        if active is None:
            tokens = TokensSnapshot()
        else:
            # El máximo de contexto: primero la detección del server, si no, el .env/UI.
            ctx_max = self.monitor.context_detected or s.context_window
            tokens = active.snapshot(now, context_max=ctx_max)
        return tokens

    # ── cierre del frame: energía, costes, alertas, persistencia ─────────────

    def _finalize(self, frame: TelemetryFrame, now: float, dt: float, s: RuntimeSettings) -> TelemetryFrame:
        # Agregados de GPU (una tarjeta por GPU + promedios para las gráficas).
        utils = [g.utilization_pct for g in frame.gpus if g.utilization_pct is not None]
        vrams = [g.memory_pct for g in frame.gpus if g.memory_pct is not None]
        temps = [g.temperature_c for g in frame.gpus if g.temperature_c is not None]
        frame.gpu_avg_pct = round(sum(utils) / len(utils), 1) if utils else None
        frame.vram_avg_pct = round(sum(vrams) / len(vrams), 1) if vrams else None
        frame.gpu_temp_max_c = round(max(temps), 1) if temps else None

        # ── potencia: suma sobre GPUs con datos ──────────────────────────────
        powers = [g.power_w for g in frame.gpus if g.power_w is not None]
        limits = [g.power_limit_w for g in frame.gpus if g.power_limit_w is not None]
        power_avail = bool(powers)
        current_w = round(sum(powers), 1) if power_avail else None
        limit_w = round(sum(limits), 1) if limits and any(l > 0 for l in limits) else None
        if power_avail and current_w is not None:
            self._energy_session_wh += energy_wh(current_w, min(dt, _ENERGY_DT_MAX_S))
        frame.power = PowerSnapshot(
            current_w=current_w,
            limit_w=limit_w,
            percent=round(current_w / limit_w * 100, 1) if current_w is not None and limit_w else None,
            energy_session_wh=round(self._energy_session_wh, 1),
            energy_session_kwh=round(self._energy_session_wh / 1000, 4),
            available=power_avail,
        )

        # ── coste ────────────────────────────────────────────────────────────
        daily_cost = self.store.energy_since(start_of_day_ts(now)) / 1000.0 * s.price_per_kwh
        cph = cost_per_hour(current_w, s.price_per_kwh)
        proj_day, proj_month = projected_costs(cph)
        frame.cost = CostSnapshot(
            price_per_kwh=s.price_per_kwh,
            session_cost=session_cost_eur(self._energy_session_wh, s.price_per_kwh),
            cost_per_hour=cph,
            projection_day=proj_day,
            projection_month=proj_month,
            cost_per_1k_tokens=cost_per_1k_tokens(
                session_cost_eur(self._energy_session_wh, s.price_per_kwh),
                frame.tokens.output_tokens,
            ),
            daily_cost=round(daily_cost, 4),
            daily_limit=s.thresholds.daily_cost_eur,
            daily_pct=(
                round(daily_cost / s.thresholds.daily_cost_eur * 100, 1)
                if s.thresholds.daily_cost_eur > 0
                else None
            ),
        )

        # ── alertas (y webhook opcional) ─────────────────────────────────────
        active, to_notify = self._alerts.evaluate(
            AlertValues(
                context_pct=frame.tokens.context.percent,
                ram_pct=frame.system.ram_pct,
                daily_cost=frame.cost.daily_cost,
                gpus=frame.gpus,
            ),
            s.thresholds,
            now,
        )
        frame.alerts = active
        self._notify(alerts=to_notify)

        # ── persistencia + poda periódica ────────────────────────────────────
        self._store_sample(frame)
        self._tick_count += 1
        if self._tick_count % _PRUNE_EVERY_TICKS == 0:
            pruned = self.store.prune(s.history_retention_hours)
            if pruned:
                log.info("Poda del histórico: %d muestras borradas (retención %dh)", pruned, s.history_retention_hours)

        self._last_tick_ts = now
        return frame

    def _store_sample(self, frame: TelemetryFrame) -> None:
        try:
            # Se guarda la energía CONSUMIDA EN ESTE TICK (delta), no la acumulada:
            # el coste diario se obtiene sumando estos deltas.
            energy_delta = max(0.0, self._energy_session_wh - self._last_stored_energy_wh)
            self._last_stored_energy_wh = self._energy_session_wh
            self.store.insert_sample(
                ts=frame.ts,
                payload=frame.to_dict(),
                input_total=frame.tokens.input_tokens,
                output_total=frame.tokens.output_tokens,
                moving_avg_tps=frame.tokens.moving_avg_output_per_s,
                context_pct=frame.tokens.context.percent,
                gpu_pct=frame.gpu_avg_pct,
                gpu_temp_c=frame.gpu_temp_max_c,
                vram_pct=frame.vram_avg_pct,
                power_w=frame.power.current_w,
                energy_delta_wh=round(energy_delta, 6),
                ram_pct=frame.system.ram_pct,
                cpu_pct=frame.system.cpu_pct,
                cost_per_hour=frame.cost.cost_per_hour,
            )
        except Exception:  # noqa: BLE001 — la app sobrevive sin histórico
            log.exception("Fallo insertando muestra en SQLite")

    async def _emit(self, frame: TelemetryFrame) -> None:
        self._latest_frame = frame
        await self._publish(_frame_json(frame))

    def _notify(self, alerts: list) -> None:
        """Webhook opcional para las alertas nuevas/escaladas."""
        import asyncio
        from app.telemetry.notifier import send_webhook as _hook

        url = self.settings.get().webhook_url
        if not url or not alerts:
            return
        for alert in alerts:
            asyncio.create_task(
                _hook(self._webhook_client, url, asdict(alert))
            )

    # ── manera de revertir settings/cambios de proveedor ────────────────────

    def reconfigure(self, s: RuntimeSettings) -> None:
        """Hook al cambiar settings: reconstruye el proveedor de GPU si cambió."""
        if s.gpu_provider != self._provider_kind:
            self._provider_kind = s.gpu_provider
            from app.metrics.base import create_provider
            from app.config import get_config

            self.provider = create_provider(s.gpu_provider, get_config())
            log.info("Proveedor de GPU reconstruido → %s", self.provider.name)

    def reset_session(self) -> None:
        """Reinicia los contadores de la sesión (tokens, energía y estado simulado)."""
        for agg in self.aggregators.values():
            agg.reset_session()
        self.simulator.reset()
        self._energy_session_wh = 0.0
        self._last_stored_energy_wh = 0.0
        self._alerts.reset()
        log.info("Sesión de métricas reiniciada")
