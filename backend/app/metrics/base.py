"""Interfaz común de proveedores de GPU y fábrica.

Cualquier hardware nuevo solo necesita implementar ``_sample_impl()`` devolviendo una
lista de ``GpuReading`` (una por tarjeta). Los campos que el hardware no reporte van a
``None`` y la UI los muestra como "sin datos".
"""

from __future__ import annotations

import asyncio
import abc
import logging
import shutil
import sys

from app.config import AppConfig
from app.core.models import GpuReading

log = logging.getLogger(__name__)


class GpuProvider(abc.ABC):
    """Contrato de un proveedor de métricas de GPU."""

    name: str = "base"

    def __init__(self) -> None:
        self.available: bool = False
        self.error: str | None = None

    @abc.abstractmethod
    def _sample_impl(self) -> list[GpuReading]:
        """Muestreo bloqueante (se ejecuta en un thread del event loop)."""

    async def sample(self) -> list[GpuReading]:
        """Muestreo asíncrono: nunca lanza excepciones, devuelve ``[]`` si falla."""
        try:
            return await asyncio.to_thread(self._sample_impl)
        except Exception as exc:  # noqa: BLE001 — robustez ante NVML/drivers rotos
            log.warning("GpuProvider[%s] fallo de muestreo: %s", self.name, exc)
            self.error = str(exc)
            return []


class NoGpuProvider(GpuProvider):
    """Proveedor nulo: no hay GPU accesible; el dashboard mostrará 'sin datos'."""

    name = "none"

    def __init__(self, message: str = "No hay GPU accesible") -> None:
        super().__init__()
        self.error = message

    def _sample_impl(self) -> list[GpuReading]:
        return []


def create_provider(kind: str, config: AppConfig) -> GpuProvider:
    """Construye el proveedor indicado, con auto-detección para ``kind='auto'``."""
    if kind == "nvidia":
        from app.metrics.nvidia import NvidiaProvider

        return NvidiaProvider()
    if kind == "amd":
        from app.metrics.amd import AmdProvider

        return AmdProvider()
    if kind == "apple":
        from app.metrics.apple import AppleProvider

        return AppleProvider()
    if kind == "none":
        return NoGpuProvider("Proveedor de GPU desactivado en ajustes")

    # ── auto-detección ───────────────────────────────────────────────────────
    from app.metrics.nvidia import NvidiaProvider

    nvidia = NvidiaProvider()
    if nvidia.available:
        return nvidia

    if shutil.which("rocm-smi"):
        from app.metrics.amd import AmdProvider

        return AmdProvider()

    if sys.platform == "darwin":
        from app.metrics.apple import AppleProvider

        return AppleProvider()

    return NoGpuProvider(
        "No se detectó GPU compatible (pynvml o rocm-smi). "
        "Puedes usar el modo simulación o ajustar el proveedor en Ajustes."
    )
