"""Métricas de tokens vía Prometheus /metrics y health del servidor de inferencia.

Soporta llama.cpp y vLLM (nombres de counters más comunes, con match por sufijo para
tolerar prefijos como ``llamacpp:`` o ``vllm:``). Es best-effort: si el endpoint no
expone métricas, ``prometheus_active`` queda ``False`` y la fuente "auto" recae en
el proxy OpenAI-compatible.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass

import httpx

from app.core.models import InferenceStatus
from app.core.settings import SettingsManager
from app.core.tokens import TokenAggregator

log = logging.getLogger(__name__)

METRICS_POLL_S = 5.0
HEALTH_POLL_S = 15.0
CONTEXT_POLL_S = 60.0

# ── parsing Prometheus (función pura, sin estado) ────────────────────────────

_SAMPLE_RE = re.compile(
    r"^(?P<name>[a-zA-Z_:][a-zA-Z0-9_:]*)(?:\{[^}]*\})?\s+(?P<value>-?\d+(?:\.\d+)?(?:e[-+]?\d+)?)\s*$",
    re.MULTILINE,
)

_INPUT_COUNTERS = ("prompt_tokens_total", "tokens_evaluated_total", "input_tokens_total")
_OUTPUT_COUNTERS = ("tokens_predicted_total", "generation_tokens_total", "output_tokens_total")


@dataclass(frozen=True)
class PrometheusCounters:
    """Valores acumulados leídos de /metrics (counter desde el arranque del server)."""

    input_total: float | None
    output_total: float | None
    engine: str

    @property
    def detected(self) -> bool:
        return self.input_total is not None or self.output_total is not None


def parse_prometheus_counters(text: str) -> PrometheusCounters:
    """Suma todos los valores de los counters de tokens de un payload Prometheus."""
    totals: dict[str, float] = {}
    engine = ""
    for match in _SAMPLE_RE.finditer(text or ""):
        name = match.group("name")
        try:
            totals[name] = totals.get(name, 0.0) + float(match.group("value"))
        except ValueError:
            continue
        if not engine and ":" in name:
            engine = name.split(":", 1)[0]

    input_total = _sum_family(totals, _INPUT_COUNTERS)
    output_total = _sum_family(totals, _OUTPUT_COUNTERS)
    return PrometheusCounters(input_total=input_total, output_total=output_total, engine=engine)


def _sum_family(totals: dict[str, float], suffixes: tuple[str, ...]) -> float | None:
    for suffix in suffixes:
        vals = [v for name, v in totals.items() if name.endswith(suffix)]
        if vals:
            return sum(vals)
    return None


class InferenceMonitor:
    """Sondea salud, /metrics (tokens Prometheus) y ventana de contexto del servidor.

    Todos los polls son asíncronos y throttled (intervalos fijados arriba) para no
    saturar al servidor de inferencia. Cualquier fallo se registra y degrada el estado
    a "offline"/inactivo sin romper el muestreo.
    """

    def __init__(
        self,
        settings: SettingsManager,
        client: httpx.AsyncClient,
        prometheus_aggregator: TokenAggregator,
    ) -> None:
        self._settings = settings
        self._client = client
        self._prometheus_agg = prometheus_aggregator

        self._last_health = 0.0
        self._last_metrics = 0.0
        self._healthy = False
        self._latency_ms: float | None = None
        self._engine = ""
        self._model = ""
        self._error: str | None = None

        # Estado del sondeo Prometheus: últimos counters vistos (para deltas) y
        # si el último payload contenía counters de tokens.
        self._prev_input: float | None = None
        self._prev_output: float | None = None
        self._prom_active = False

        # Detección de ventana de contexto (Ollama /api/ps, llama.cpp /props).
        self._ctx_detected: int | None = None
        self._ctx_source = ""
        self._last_ctx_poll = 0.0

    # ── interface para el sampler ────────────────────────────────────────────

    @property
    def prometheus_active(self) -> bool:
        return self._prom_active

    @property
    def context_detected(self) -> int | None:
        return self._ctx_detected

    @property
    def context_source(self) -> str:
        return self._ctx_source

    async def poll(self, now: float) -> InferenceStatus:
        """Realiza los poll throttled y devuelve el estado para el frame."""
        await self._poll_health(now)
        await self._poll_metrics(now)
        await self._poll_context(now)
        s = self._settings.get()
        return InferenceStatus(
            status="online" if self._healthy else "offline",
            engine=self._engine,
            model=self._model or s.inference_model,
            latency_ms=self._latency_ms,
            error=self._error,
            context_hint_tokens=self._ctx_detected,
            context_hint_source=self._ctx_source,
        )

    # ── salud ────────────────────────────────────────────────────────────────

    async def _poll_health(self, now: float) -> None:
        base = self._settings.get().inference_base_url
        if not base:
            self._healthy = False
            self._error = "URL de inferencia no configurada"
            return
        if (now - self._last_health) < HEALTH_POLL_S and self._latency_ms is not None:
            return
        self._last_health = now
        try:
            t0 = time.perf_counter()
            resp = await self._client.get(f"{base}/models", headers=self._auth_headers(), timeout=3)
            self._latency_ms = round((time.perf_counter() - t0) * 1000, 1)
            if resp.status_code == 200:
                self._healthy = True
                self._error = None
                models = (resp.json() or {}).get("data") or []
                if models and models[0].get("id"):
                    self._model = str(models[0]["id"])
            else:
                self._healthy = False
                self._error = f"HTTP {resp.status_code} en {base}/models"
        except Exception as exc:  # noqa: BLE001
            self._healthy = False
            self._error = f"Sin conexión con el servidor de inferencia ({type(exc).__name__})"
            self._latency_ms = None

    # ── Prometheus /metrics ──────────────────────────────────────────────────

    async def _poll_metrics(self, now: float) -> None:
        s = self._settings.get()
        metrics_url = s.inference_metrics_url or self._infer_metrics_url(s.inference_base_url)
        if not metrics_url:
            return
        if (now - self._last_metrics) < METRICS_POLL_S:
            return
        dt = max(0.5, now - self._last_metrics) if self._last_metrics else METRICS_POLL_S
        self._last_metrics = now
        try:
            resp = await self._client.get(metrics_url, headers=self._auth_headers(), timeout=3)
            if resp.status_code != 200:
                self._prom_active = False
                return
            counters = parse_prometheus_counters(resp.text)
            if not counters.detected:
                self._prom_active = False
                return
            input_delta = 0
            output_delta = 0
            if counters.input_total is not None and self._prev_input is not None:
                input_delta = max(0, int(counters.input_total - self._prev_input))
            if counters.output_total is not None and self._prev_output is not None:
                output_delta = max(0, int(counters.output_total - self._prev_output))
            # Guarda baselines (si el server se reinicia, counter menor → delta=0 y re-base).
            self._prev_input = counters.input_total
            self._prev_output = counters.output_total
            self._prometheus_agg.record_tick(
                ts=now, input_delta=input_delta, output_delta=output_delta, dt_s=dt
            )
            self._engine = counters.engine or self._engine
            self._prom_active = True
        except Exception:  # noqa: BLE001 — /metrics suele ser opcional
            self._prom_active = False

    # ── ventana de contexto ──────────────────────────────────────────────────

    async def _poll_context(self, now: float) -> None:
        base = self._settings.get().inference_base_url
        if not base or self._ctx_detected is not None:
            return
        if (now - self._last_ctx_poll) < CONTEXT_POLL_S:
            return
        self._last_ctx_poll = now
        root = base.rsplit("/v1", 1)[0] if base.endswith("/v1") else base
        # 1) Ollama: /api/ps → models[0].context_length
        try:
            resp = await self._client.get(f"{root}/api/ps", timeout=2)
            if resp.status_code == 200:
                models = (resp.json() or {}).get("models") or []
                ctx = (models[0] or {}).get("context_length") if models else None
                if ctx:
                    self._ctx_detected = int(ctx)
                    self._ctx_source = "ollama"
                    log.info("Ventana de contexto detectada (Ollama): %d", ctx)
                    return
        except Exception:  # noqa: BLE001
            pass
        # 2) llama.cpp: /props → default_generation_settings.n_ctx
        try:
            resp = await self._client.get(f"{root}/props", timeout=2)
            if resp.status_code == 200:
                n_ctx = (resp.json() or {}).get("default_generation_settings", {}).get("n_ctx")
                if n_ctx:
                    self._ctx_detected = int(n_ctx)
                    self._ctx_source = "llamacpp"
                    log.info("Ventana de contexto detectada (llama.cpp): %d", n_ctx)
        except Exception:  # noqa: BLE001
            pass

    # ── helpers ──────────────────────────────────────────────────────────────

    def _auth_headers(self) -> dict[str, str]:
        key = self._settings.get().inference_api_key
        return {"Authorization": f"Bearer {key}"} if key else {}

    @staticmethod
    def _infer_metrics_url(base: str) -> str:
        """Deducir ``{root}/metrics`` a partir de la URL OpenAI-compatible."""
        if not base:
            return ""
        root = base.rsplit("/v1", 1)[0] if base.endswith("/v1") else base
        return f"{root}/metrics"
