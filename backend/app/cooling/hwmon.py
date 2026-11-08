"""Sensores y ventiladores del sistema vía hwmon (sysfs de Linux).

Soporta las placas base/sensores expuestos por ``lm-sensors`` (nct6775, it87,
k10temp, coretemp, nvme, etc.). La lectura funciona en modo solo lectura; la
escritura de PWM requiere que el backend pueda escribir en sysfs y que
``COOLING_CONTROL_ENABLED=true``.

Fail-safe:
- El canal se considera controlable solo si ``pwm*`` es escribible.
- Se guarda el ``pwm*_enable`` original para poder restaurar el control de la BIOS.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_CPU_HINTS = ("coretemp", "k10temp", "zenpower", "cpu", "package", "tctl", "tdie")
_STORAGE_HINTS = ("nvme", "composite", "ssd")
_PUMP_HINTS = ("pump", "water", "aio", "bomba")


@dataclass
class FanChannel:
    id: str
    label: str
    kind: str = "system"
    source: str = "hwmon"
    rpm: int | None = None
    pwm_pct: int | None = None
    controllable: bool = False
    min_pwm_pct: float = 20.0
    last_error: str | None = None
    is_protected: bool = False
    pwm_path: Path | None = field(default=None, repr=False)
    enable_path: Path | None = field(default=None, repr=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "kind": self.kind,
            "source": self.source,
            "rpm": self.rpm,
            "pwm_pct": self.pwm_pct,
            "controllable": self.controllable,
            "min_pwm_pct": self.min_pwm_pct,
            "last_error": self.last_error,
            "is_protected": self.is_protected,
        }


@dataclass
class HwmonScan:
    temperatures: list[dict[str, Any]] = field(default_factory=list)
    fans: list[FanChannel] = field(default_factory=list)
    writable: bool = False
    error: str | None = None


class HwmonProvider:
    """Escanea ``/sys/class/hwmon`` y aplica PWM a los ventiladores."""

    def __init__(self, root: str, control_enabled: bool, min_pwm: float) -> None:
        self.root = Path(root)
        self.control_enabled = control_enabled
        self.min_pwm = min_pwm
        self._fan_map: dict[str, FanChannel] = {}
        self._original_enable: dict[str, int] = {}

    def scan(self) -> HwmonScan:
        self._fan_map = {}
        result = HwmonScan()
        if not self.root.exists():
            result.error = f"hwmon no accesible en {self.root}"
            return result

        seen_ids: set[str] = set()
        for hwmon in sorted(self.root.glob("hwmon*")):
            try:
                chip = _read_text(hwmon / "name") or hwmon.name
            except OSError:
                continue

            for temp_input in sorted(hwmon.glob("temp*_input")):
                index = _channel_index(temp_input.name, "temp")
                if index is None:
                    continue
                raw = _read_int(temp_input)
                if raw is None or raw <= 0:
                    continue
                value_c = round(raw / 1000.0, 1)
                if value_c > 150:
                    continue
                label = _read_text(hwmon / f"temp{index}_label") or f"{chip} Sensor {index}"
                source = _classify_temperature(chip, label)
                temp_id = _unique_id(f"{_slug(chip)}-temp{index}", seen_ids)
                result.temperatures.append(
                    {
                        "id": temp_id,
                        "label": label,
                        "source": source,
                        "value_c": value_c,
                        "chip": chip,
                    }
                )

            for fan_input in sorted(hwmon.glob("fan*_input")):
                index = _channel_index(fan_input.name, "fan")
                if index is None:
                    continue
                rpm = _read_int(fan_input)
                pwm_path = hwmon / f"pwm{index}"
                enable_path = hwmon / f"pwm{index}_enable"
                pwm_pct = None
                if pwm_path.exists():
                    raw_pwm = _read_int(pwm_path)
                    if raw_pwm is not None:
                        pwm_pct = round(min(100, max(0, raw_pwm / 255.0 * 100.0)))
                label = _read_text(hwmon / f"fan{index}_label") or f"{chip} Fan {index}"
                fan_id = _unique_id(f"{_slug(chip)}-fan{index}", seen_ids)
                is_pump = any(hint in label.lower() for hint in _PUMP_HINTS)
                writable = (
                    self.control_enabled
                    and pwm_path.exists()
                    and os.access(pwm_path, os.W_OK)
                    and not is_pump
                )
                channel = FanChannel(
                    id=fan_id,
                    label=label,
                    rpm=rpm,
                    pwm_pct=pwm_pct,
                    controllable=writable,
                    min_pwm_pct=self.min_pwm,
                    is_protected=is_pump,
                    pwm_path=pwm_path if pwm_path.exists() else None,
                    enable_path=enable_path if enable_path.exists() else None,
                )
                self._fan_map[fan_id] = channel
                result.fans.append(channel)
                if writable:
                    result.writable = True

        result.fans.sort(key=lambda f: f.label.lower())
        result.temperatures.sort(key=lambda t: (t["source"] != "cpu", t["source"] != "gpu", t["label"]))
        if not result.temperatures and not result.fans and result.error is None:
            result.error = "No se encontraron sensores/fans en hwmon"
        return result

    def set_pwm(self, fan_id: str, pwm_pct: int) -> str | None:
        """Aplica un PWM a un ventilador. Devuelve un error o ``None``."""
        channel = self._fan_map.get(fan_id)
        if channel is None or channel.pwm_path is None:
            return "Ventilador no encontrado"
        if not self.control_enabled:
            return "Control de refrigeración desactivado"
        if not channel.controllable:
            return "Este ventilador no permite escritura PWM"
        try:
            if channel.enable_path is not None:
                original = self._original_enable.setdefault(fan_id, _read_int(channel.enable_path) or 0)
                current = _read_int(channel.enable_path)
                if current != 1:
                    channel.enable_path.write_text("1", encoding="ascii")
            raw = round(max(0, min(100, pwm_pct)) / 100.0 * 255)
            channel.pwm_path.write_text(str(raw), encoding="ascii")
            channel.pwm_pct = int(pwm_pct)
            channel.last_error = None
            return None
        except OSError as exc:
            channel.last_error = str(exc)
            log.warning("No se pudo escribir PWM en %s: %s", channel.pwm_path, exc)
            return str(exc)

    def restore_all(self) -> None:
        """Devuelve el control de los ventiladores a la BIOS/EC."""
        for fan_id, original in self._original_enable.items():
            channel = self._fan_map.get(fan_id)
            if channel and channel.enable_path is not None:
                try:
                    channel.enable_path.write_text(str(original), encoding="ascii")
                except OSError as exc:  # noqa: PERF203
                    log.warning("No se pudo restaurar %s: %s", channel.enable_path, exc)
        self._original_enable.clear()


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None


def _read_int(path: Path) -> int | None:
    raw = _read_text(path)
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _channel_index(filename: str, prefix: str) -> int | None:
    match = re.fullmatch(rf"{prefix}(\d+)_input", filename)
    return int(match.group(1)) if match else None


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or "hwmon"


def _unique_id(candidate: str, seen: set[str]) -> str:
    value = candidate
    suffix = 2
    while value in seen:
        value = f"{candidate}-{suffix}"
        suffix += 1
    seen.add(value)
    return value


def _classify_temperature(chip: str, label: str) -> str:
    text = f"{chip} {label}".lower()
    if any(hint in text for hint in _CPU_HINTS):
        return "cpu"
    if any(hint in text for hint in _STORAGE_HINTS):
        return "storage"
    return "system"
