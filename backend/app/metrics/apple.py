"""Proveedor para Apple Silicon (punto de extensión preparado).

En macOS los datos de GPU están en ``powermetrics``, que requiere ejecutar con sudo:
``powermetrics -n 1 -i 1000 --samplers gpu_power``. El proveedor intenta leer
"GPU Power" y la residencia activa del GPU; si no tiene permisos, devuelve ``[]``
con un mensaje descriptivo y el dashboard muestra "sin datos".

VRAM: en Apple Silicon la memoria es unificada, así que el uso de GPU se aproxima con
la RAM del sistema (psutil). Amplía aquí si necesitas más detalle (Metal/IOKit).
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
import sys

from app.core.models import GpuReading
from app.metrics.base import GpuProvider

log = logging.getLogger(__name__)

_POWERMETRICS_RE = re.compile(r"(GPU HW active residency|GPU Power):\s*([\d.]+)")


class AppleProvider(GpuProvider):
    name = "apple"

    def __init__(self) -> None:
        super().__init__()
        if sys.platform != "darwin":
            self.error = "AppleProvider solo funciona en macOS"
            self.available = False
        elif shutil.which("powermetrics") is None:
            self.error = "'powermetrics' no está disponible"
            self.available = False
        else:
            self.available = True

    def _sample_impl(self) -> list[GpuReading]:
        if not self.available:
            return []
        try:
            result = subprocess.run(
                ["powermetrics", "-n", "1", "-i", "200", "--samplers", "gpu_power"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode != 0:
                self.error = (
                    "powermetrics necesita permisos de administrador (ejecuta el backend "
                    "con sudo o añade el binario a sudoers sin contraseña)"
                )
                return []
        except (subprocess.SubprocessError, OSError) as exc:
            self.error = f"AppleProvider: {exc}"
            return []

        matches = _POWERMETRICS_RE.findall(result.stdout or "")
        residency = next((float(v) for k, v in matches if k.startswith("GPU HW")), None)
        power_mw = next((float(v) for k, v in matches if k == "GPU Power"), None)
        if residency is None:
            self.error = "No se encontraron métricas de GPU en powermetrics"
            return []

        return [
            GpuReading(
                index=0,
                name="Apple Silicon GPU",
                vendor="apple",
                utilization_pct=residency,
                memory_used_mb=None,  # el uso se refleja en la RAM del sistema
                memory_total_mb=None,
                temperature_c=None,
                fan_pct=None,
                power_w=power_mw / 1000 if power_mw is not None else None,
                power_limit_w=None,
            )
        ]
