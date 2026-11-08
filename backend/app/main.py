"""Punto de entrada FastAPI de Monitor IA.

Monta lifespan (DB, settings, httpx, sampler), CORS, rutas API y proxy,
y expone ``app`` para ``uvicorn app.main:app``.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from app.api.routes import router as api_router
from app.config import get_config
from app.cooling.service import CoolingService
from app.core.settings import RuntimeSettings, SettingsManager
from app.core.tokens import TokenAggregator
from app.inference.monitor import InferenceMonitor
from app.inference.proxy import router as proxy_router
from app.metrics.base import create_provider
from app.metrics.system import SystemSampler
from app.security.middleware import SecurityHTTPMiddleware, SecurityRecorder
from app.security.service import SecurityService
from app.storage.database import HistoryStore
from app.telemetry.hub import TelemetryHub
from app.telemetry.sampler import TelemetrySampler
from app.telemetry.simulator import Simulator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
)
log = logging.getLogger("monitor-ia")


def create_app() -> FastAPI:
    config = get_config()
    store = HistoryStore(config.db_file)
    persisted = store.load_runtime_settings()
    log.info("Settings runtime cargados desde SQLite: %s", bool(persisted))

    # El sampler se reconfigura cuando cambian los settings desde la UI.
    sampler_ref: dict[str, TelemetrySampler | None] = {"sampler": None}
    settings = SettingsManager(
        RuntimeSettings.from_config(config, persisted),
        on_change=lambda s: sampler_ref["sampler"].reconfigure(s) if sampler_ref["sampler"] else None,
    )

    provider = create_provider(settings.get().gpu_provider, config)
    if not provider.available:
        log.warning("GPU: %s — el dashboard mostrará 'sin datos' en tarjetas de GPU", provider.error)

    aggregators = {
        "proxy": TokenAggregator("proxy"),
        "prometheus": TokenAggregator("prometheus"),
        "simulation": TokenAggregator("simulation"),
    }
    simulator = Simulator(config)
    system_sampler = SystemSampler()
    security_recorder = SecurityRecorder(enabled=config.security_enabled)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        http = httpx.AsyncClient(
            timeout=httpx.Timeout(10.0, connect=5.0),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )
        monitor = InferenceMonitor(settings, http, aggregators["prometheus"])
        hub = TelemetryHub()
        sampler = TelemetrySampler(
            settings=settings,
            store=store,
            provider=provider,
            monitor=monitor,
            simulator=simulator,
            aggregators=aggregators,
            system_sampler=system_sampler,
            publish=hub.broadcast,
            webhook_client=http,
        )
        security = SecurityService(config, store, http, security_recorder)
        cooling = CoolingService(config, store, settings)
        sampler_ref["sampler"] = sampler

        app.state.telemetry_sampler = sampler
        app.state.telemetry_hub = hub
        app.state.settings_manager = settings
        app.state.history_store = store
        app.state.inference_monitor = monitor
        app.state.http_client = http
        app.state.security_service = security
        app.state.security_recorder = security_recorder
        app.state.cooling_service = cooling
        # El proxy necesita acceso al agregador de tokens vía proxy y al monitor.
        app.state.proxy_aggregator = aggregators["proxy"]
        app.state.token_aggregators = aggregators

        if not settings.get().simulation_mode:
            log.info("MODO LIVE: proveedor GPU=%s | inferencia=%s", provider.name, settings.get().inference_base_url)
        # El primer arranque del sampler ocurre tras completar el estado de la app.
        await sampler.start()
        await security.start()
        await cooling.start()
        log.info("Monitor IA listo (intervalo=%dms, simulación=%s)", settings.get().refresh_interval_s * 1000, settings.get().simulation_mode)
        try:
            yield
        finally:
            await sampler.stop()
            await security.stop()
            await cooling.stop()
            await http.aclose()
            store.close()
            log.info("Monitor IA detenido")

    app = FastAPI(
        title="Monitor IA",
        description="Observabilidad de inferencia de IA en local: tokens, contexto, GPU, potencia y coste energético.",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.state.config = config

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # dashboard en LAN/VPN; el backend no expone secretos
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    app.add_middleware(SecurityHTTPMiddleware, recorder=security_recorder)

    app.include_router(api_router)
    app.include_router(proxy_router)
    return app


app = create_app()


if __name__ == "__main__":  # python -m app.main
    import uvicorn

    config = get_config()
    uvicorn.run("app.main:app", host=config.app_host, port=config.app_port, log_level="info")
