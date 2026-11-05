"""Proveedor AMD vía ``rocm-smi`` (ROCm).

Se invoca ``rocm-smi --json`` (bloqueante, en un thread) y se parsean los documentos
JSON concatenados que genera la herramienta. Es best-effort: los nombres de claves
varían entre versiones de ROCm, por eso se usan búsquedas por fragmentos.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from typing import Any

from app.core.models import GpuReading
from app.metrics.base import GpuProvider

log = logging.getLogger(__name__)


class AmdProvider(GpuProvider):
    name = "amd"

    def __init__(self) -> None:
        super().__init__()
        if shutil.which("rocm-smi") is None:
            self.error = "El binario 'rocm-smi' no está disponible en PATH"
            self.available = False
        else:
            self.available = True

    def _sample_impl(self) -> list[GpuReading]:
        if not self.available:
            return []
        try:
            result = subprocess.run(
                ["rocm-smi", "--json", "--showuse", "--showvramuse", "--showtemp", "--showfan", "--showpower"],
                capture_output=True,
                text=True,
                timeout=4,
                check=True,
            )
        except (subprocess.SubprocessError, OSError) as exc:
            self.error = f"rocm-smi falló: {exc}"
            log.warning("AmdProvider: %s", self.error)
            return []

        cards = _parse_cards(result.stdout)
        readings: list[GpuReading] = []
        for idx, card in cards.items():
            readings.append(
                GpuReading(
                    index=idx,
                    name=f"AMD GPU {idx}",
                    vendor="amd",
                    utilization_pct=_float(card, "gpu use", "utilization"),
                    memory_used_mb=_float(card, "vram", "used") / 1024**2 if _float(card, "vram", "used") else None,
                    memory_total_mb=_float(card, "vram", "total memory") / 1024**2 if _float(card, "vram", "total memory") else None,
                    temperature_c=_float(card, "temperature", "edge") or _float(card, "temperature", "junction"),
                    fan_pct=_float(card, "fan"),
                    power_w=_float(card, "power (w)"),
                    power_limit_w=None,  # rocm-smi no publica el TDP de forma estable
                )
            )
        return readings


def _parse_cards(text: str) -> dict[int, dict[str, Any]]:
    """``rocm-smi --json`` concatena varios documentos JSON; se trocea y se fusiona."""
    docs: list[dict[str, Any]] = []
    depth = 0
    start = -1
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}" and start >= 0:
            depth -= 1
            if depth == 0:
                try:
                    docs.append(json.loads(text[start : i + 1]))
                except json.JSONDecodeError:
                    pass
                start = -1

    cards: dict[int, dict[str, Any]] = {}
    for doc in docs:
        for key, value in doc.items():
            k = str(key).lower()
            if k.startswith("card"):
                try:
                    card_idx = int(k.split("card")[1].split("[")[0])
                except (ValueError, IndexError):
                    card_idx = len(cards)
                cards.setdefault(card_idx, {}).update(value or {})
    return {k: cards[k] for k in sorted(cards)}


def _float(card: dict[str, Any], *fragments: str) -> float | None:
    """Busca una clave cuyo nombre (lowercase) contenga todos los fragmentos."""
    for key, value in card.items():
        k = str(key).lower()
        if all(f.lower() in k for f in fragments):
            try:
                return float(str(value).replace("%", "").strip())
            except (TypeError, ValueError):
                continue
    return None
