"""Integración con servidores de inferencia OpenAI-compatibles.

- ``monitor``: salud del servidor, lectura de counters Prometheus, detección de
  ventana de contexto (Ollama/llama.cpp).
- ``proxy``   : pasarela OpenAI-compatible que captura el ``usage`` de cada respuesta
  (streaming y no-streaming) para alimentar las métricas de tokens/contexto.
"""

from app.inference.monitor import InferenceMonitor, PrometheusCounters, parse_prometheus_counters
from app.inference.proxy import router as proxy_router

__all__ = [
    "InferenceMonitor",
    "PrometheusCounters",
    "parse_prometheus_counters",
    "proxy_router",
]
