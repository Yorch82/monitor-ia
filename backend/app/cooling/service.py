"""Servicio de refrigeración: recolección, perfiles, control seguro y snapshot."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from app.config import AppConfig
from app.cooling.gpu_fans import GpuFanController
from app.cooling.hwmon import HwmonProvider
from app.cooling.profiles import (
    DEFAULT_PROFILE,
    PROFILE_INFO,
    SELECTABLE_PROFILES,
    clamp_pwm,
    target_for_profile,
)
from app.cooling.simulator import CoolingSimulator
from app.core.settings import SettingsManager
from app.storage.database import HistoryStore

log = logging.getLogger(__name__)


class CoolingError(Exception):
    """Error de dominio con status HTTP para la API."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


class CoolingService:
    """Orquesta sensores, perfiles y control de ventiladores.

    El control es opt-in (``COOLING_CONTROL_ENABLED``) y fail-safe: nunca baja del
    PWM mínimo, fuerza 100 % en emergencia térmica y restaura el control de la BIOS
    al salir si ``COOLING_RESTORE_ON_EXIT`` está activo.
    """

    def __init__(
        self,
        config: AppConfig,
        store: HistoryStore,
        settings: SettingsManager,
    ) -> None:
        self.config = config
        self.store = store
        self.settings = settings
        self.min_pwm = float(config.cooling_min_pwm_pct)
        self.emergency_temp = float(config.cooling_emergency_temp_c)
        self.emergency_release = float(config.cooling_emergency_release_c)

        self.hwmon = HwmonProvider(
            config.cooling_hwmon_root,
            control_enabled=config.cooling_control_enabled,
            min_pwm=self.min_pwm,
            protected_ids=config.cooling_protected_fan_list,
        )
        self.gpu = GpuFanController(
            control_enabled=config.cooling_control_enabled,
            gpu_fans_enabled=config.cooling_gpu_fans_enabled,
            min_pwm=self.min_pwm,
        )
        self.simulator = CoolingSimulator(min_pwm=self.min_pwm)

        state = store.load_cooling_state() or {}
        loaded_profile = str(state.get("profile", DEFAULT_PROFILE))
        self.profile = loaded_profile if loaded_profile in (*SELECTABLE_PROFILES, "custom") else DEFAULT_PROFILE
        self.overrides: dict[str, int] = {
            str(k): clamp_pwm(float(v), self.min_pwm)
            for k, v in (state.get("overrides") or {}).items()
            if isinstance(v, (int, float))
        }
        self.released = bool(state.get("released", False))
        self.emergency_active = False
        self.last_error: str | None = None
        self._last_snapshot: dict[str, Any] | None = None
        self._task: asyncio.Task | None = None

    # ── ciclo de vida ────────────────────────────────────────────────────────

    async def start(self) -> None:
        try:
            self.refresh()
        except Exception as exc:  # noqa: BLE001
            log.warning("Cooling: error en el primer muestreo: %s", exc)
        self._task = asyncio.create_task(self._loop(), name="cooling-monitor")
        log.info(
            "Refrigeración: monitor iniciado (control=%s, gpu_fans=%s, hwmon=%s)",
            self.config.cooling_control_enabled,
            self.config.cooling_gpu_fans_enabled,
            self.config.cooling_hwmon_root,
        )

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self.config.cooling_restore_on_exit and self.config.cooling_control_enabled:
            self.hwmon.restore_all()
            self.gpu.restore_all()
            log.info("Refrigeración: control devuelto a la BIOS al detener")

    async def _loop(self) -> None:
        interval = max(0.5, self.config.cooling_poll_interval_ms / 1000.0)
        while True:
            await asyncio.sleep(interval)
            try:
                self.refresh()
            except Exception as exc:  # noqa: BLE001
                self.last_error = str(exc)
                log.warning("Cooling: fallo de muestreo: %s", exc)

    # ── API ──────────────────────────────────────────────────────────────────

    def snapshot(self) -> dict[str, Any]:
        if self._last_snapshot is None:
            self.refresh()
        return self._last_snapshot or self._empty_snapshot("Sin datos de refrigeración")

    def set_profile(self, profile: str) -> dict[str, Any]:
        if profile not in SELECTABLE_PROFILES:
            raise CoolingError("Perfil de refrigeración inválido", 400)
        self._require_control()
        self.profile = profile
        self.overrides.clear()
        self.released = False
        self._save_state()
        self.refresh()
        return self.snapshot()

    def set_fan_pwm(self, fan_id: str, pwm_pct: float) -> dict[str, Any]:
        self._require_control()
        current = self._last_snapshot or self.snapshot()
        fans = current.get("fans", [])
        fan = next((f for f in fans if f.get("id") == fan_id), None)
        if fan is None:
            raise CoolingError("Ventilador no encontrado", 404)
        if not fan.get("controllable"):
            raise CoolingError("Este ventilador no se puede controlar", 409)
        target = clamp_pwm(float(pwm_pct), float(fan.get("min_pwm_pct") or self.min_pwm))
        if self.profile != "custom":
            # Tomamos una instantánea de todas las velocidades actuales y pasamos a
            # perfil personalizado, para no alterar el resto de ventiladores.
            self.overrides = {
                str(f["id"]): int(f["pwm_pct"])
                for f in fans
                if f.get("controllable") and f.get("pwm_pct") is not None
            }
            self.profile = "custom"
        self.overrides[fan_id] = target
        self.released = False
        self._save_state()
        self.refresh()
        return self.snapshot()

    def release_to_bios(self) -> dict[str, Any]:
        self._require_control()
        simulated = self._is_simulation()
        if not simulated:
            self.hwmon.restore_all()
            self.gpu.restore_all()
        self.released = True
        self.emergency_active = False
        self._save_state()
        self.refresh()
        return self.snapshot()

    # ── muestreo ─────────────────────────────────────────────────────────────

    def refresh(self) -> None:
        self.last_error = None
        if self._is_simulation():
            self._refresh_simulation()
        else:
            self._refresh_live()

    def _refresh_simulation(self) -> None:
        temperatures = self.simulator.temperatures()
        max_temp = _max_primary_temp(temperatures)
        self._update_emergency(max_temp)

        if not self.released:
            fans = self.simulator.fans()
            targets = self._targets_for(fans, max_temp)
            for fan in fans:
                target = targets.get(fan["id"])
                if target is not None:
                    self.simulator.set_pwm(fan["id"], target)

        self.simulator.step()
        temperatures = self.simulator.temperatures()
        fans = self.simulator.fans()
        self._last_snapshot = self._build_snapshot(
            temperatures=temperatures,
            fans=fans,
            writable=True,
            simulated=True,
        )

    def _refresh_live(self) -> None:
        scan = self.hwmon.scan()
        gpu_scan = self.gpu.scan()
        temperatures = list(scan.temperatures) + list(gpu_scan["temperatures"])
        fans = [fan.to_dict() for fan in scan.fans] + list(gpu_scan["fans"])
        writable = scan.writable or gpu_scan["writable"]
        max_temp = _max_primary_temp(temperatures)
        self._update_emergency(max_temp)

        if (
            self.config.cooling_control_enabled
            and writable
            and not self.released
        ):
            targets = self._targets_for(fans, max_temp)
            self._apply_live(fans, targets)

        errors = [scan.error] if scan.error else []
        if self.gpu.error and not self.gpu.available:
            errors.append(self.gpu.error)
        if not self.last_error and errors:
            self.last_error = "; ".join(errors)

        self._last_snapshot = self._build_snapshot(
            temperatures=temperatures,
            fans=fans,
            writable=writable,
            simulated=False,
        )

    def _targets_for(self, fans: list[dict[str, Any]], max_temp: float | None) -> dict[str, int]:
        controllable = [f for f in fans if f.get("controllable") and f.get("id")]
        if self.profile == "custom":
            targets: dict[str, int] = {}
            for fan in controllable:
                value = self.overrides.get(str(fan["id"]))
                if value is not None:
                    targets[str(fan["id"])] = clamp_pwm(float(value), self.min_pwm)
            return targets

        target = 100 if self.emergency_active else target_for_profile(
            self.profile, max_temp, self.min_pwm
        )
        return {str(fan["id"]): target for fan in controllable}

    def _apply_live(self, fans: list[dict[str, Any]], targets: dict[str, int]) -> None:
        for fan in fans:
            fan_id = str(fan.get("id"))
            target = targets.get(fan_id)
            if target is None or not fan.get("controllable"):
                continue
            current = fan.get("pwm_pct")
            if current is not None and abs(int(current) - target) < 3:
                continue
            if fan.get("kind") == "gpu":
                error = self.gpu.set_pwm(fan_id, target)
            else:
                error = self.hwmon.set_pwm(fan_id, target)
            if error:
                fan["last_error"] = error
                self.last_error = f"{fan.get('label', fan_id)}: {error}"
            else:
                fan["pwm_pct"] = target
                fan["last_error"] = None

    def _update_emergency(self, max_temp: float | None) -> None:
        if max_temp is None:
            self.emergency_active = False
            return
        if max_temp >= self.emergency_temp:
            if not self.emergency_active:
                log.warning("Refrigeración: emergencia térmica a %.1f ºC", max_temp)
            self.emergency_active = True
        elif max_temp <= self.emergency_release:
            self.emergency_active = False

    # ── snapshot ─────────────────────────────────────────────────────────────

    def _build_snapshot(
        self,
        temperatures: list[dict[str, Any]],
        fans: list[dict[str, Any]],
        writable: bool,
        simulated: bool,
    ) -> dict[str, Any]:
        cpu_temp = _max_temp_for_source(temperatures, "cpu")
        gpu_temp = _max_temp_for_source(temperatures, "gpu")
        max_temp = max([t for t in (cpu_temp, gpu_temp) if t is not None], default=None)
        if max_temp is None:
            max_temp = max([float(t["value_c"]) for t in temperatures if t.get("value_c") is not None], default=None)

        rpm_values = [float(f["rpm"]) for f in fans if isinstance(f.get("rpm"), (int, float))]
        controllable = any(f.get("controllable") for f in fans)
        enabled = simulated or self.config.cooling_control_enabled

        profile = self.profile
        note = self._control_note(simulated, writable, controllable)

        temperatures_sorted = sorted(
            temperatures,
            key=lambda t: (
                {"cpu": 0, "gpu": 1, "system": 2, "storage": 3}.get(t.get("source"), 4),
                str(t.get("label", "")),
            ),
        )
        fans_sorted = sorted(
            fans,
            key=lambda f: (
                0 if f.get("kind") == "system" else 1,
                str(f.get("label", "")),
            ),
        )

        return {
            "updated_at": time.time(),
            "mode": "simulation" if simulated else "live",
            "available": bool(temperatures or fans),
            "control": {
                "enabled": enabled,
                "writable": writable and (simulated or self.config.cooling_control_enabled),
                "released": self.released,
                "profile": profile,
                "emergency_active": self.emergency_active,
                "min_pwm_pct": self.min_pwm,
                "emergency_temp_c": self.emergency_temp,
                "emergency_release_c": self.emergency_release,
                "restore_on_exit": self.config.cooling_restore_on_exit,
                "last_error": self.last_error,
                "note": note,
            },
            "summary": {
                "cpu_temp_c": cpu_temp,
                "gpu_temp_c": gpu_temp,
                "max_temp_c": max_temp,
                "fan_count": len(fans),
                "controllable_fans": sum(1 for f in fans if f.get("controllable")),
                "avg_fan_rpm": round(sum(rpm_values) / len(rpm_values), 0) if rpm_values else None,
            },
            "temperatures": temperatures_sorted,
            "fans": fans_sorted,
            "profiles": PROFILE_INFO,
        }

    def _control_note(self, simulated: bool, writable: bool, controllable: bool) -> str:
        if simulated:
            return "Modo simulación: control virtual de ventiladores."
        if not self.config.cooling_control_enabled:
            return (
                "Solo lectura. Para controlar ventiladores activa COOLING_CONTROL_ENABLED=true "
                "y monta /sys del host (docker-compose.cooling.yml)."
            )
        if self.released:
            return "Control devuelto a la BIOS/EC. Elige un perfil para volver a controlar."
        if not writable or not controllable:
            return (
                f"No se encontraron canales PWM escribibles en {self.config.cooling_hwmon_root}. "
                "Comprueba que el driver hwmon expone pwm* y los permisos del contenedor."
            )
        return (
            f"Control activo · PWM mínimo {self.min_pwm:.0f}% · "
            f"emergencia a {self.emergency_temp:.0f} ºC."
        )

    def _empty_snapshot(self, error: str) -> dict[str, Any]:
        return {
            "updated_at": time.time(),
            "mode": "simulation" if self._is_simulation() else "live",
            "available": False,
            "control": {
                "enabled": self.config.cooling_control_enabled,
                "writable": False,
                "released": self.released,
                "profile": self.profile,
                "emergency_active": False,
                "min_pwm_pct": self.min_pwm,
                "emergency_temp_c": self.emergency_temp,
                "emergency_release_c": self.emergency_release,
                "restore_on_exit": self.config.cooling_restore_on_exit,
                "last_error": error,
                "note": error,
            },
            "summary": {
                "cpu_temp_c": None,
                "gpu_temp_c": None,
                "max_temp_c": None,
                "fan_count": 0,
                "controllable_fans": 0,
                "avg_fan_rpm": None,
            },
            "temperatures": [],
            "fans": [],
            "profiles": PROFILE_INFO,
        }

    # ── helpers ──────────────────────────────────────────────────────────────

    def _is_simulation(self) -> bool:
        return self.settings.get().simulation_mode

    def _require_control(self) -> None:
        if self._is_simulation():
            return
        if not self.config.cooling_control_enabled:
            raise CoolingError(
                "El control de refrigeración está desactivado en el servidor "
                "(COOLING_CONTROL_ENABLED=false).",
                403,
            )
        snapshot = self._last_snapshot or self.snapshot()
        if not snapshot.get("control", {}).get("writable"):
            raise CoolingError(
                "No hay canales PWM escribibles. Monta /sys con permisos y comprueba hwmon.",
                409,
            )

    def _save_state(self) -> None:
        try:
            self.store.save_cooling_state(
                {
                    "profile": self.profile,
                    "overrides": self.overrides,
                    "released": self.released,
                }
            )
        except Exception:  # noqa: BLE001
            log.exception("No se pudo persistir el estado de refrigeración")


def _max_primary_temp(temperatures: list[dict[str, Any]]) -> float | None:
    """Temperatura máxima CPU/GPU (para emergencia y curva automática)."""
    values = [
        float(t["value_c"])
        for t in temperatures
        if t.get("source") in ("cpu", "gpu") and t.get("value_c") is not None
    ]
    if not values:
        values = [float(t["value_c"]) for t in temperatures if t.get("value_c") is not None]
    return max(values) if values else None


def _max_temp_for_source(temperatures: list[dict[str, Any]], source: str) -> float | None:
    values = [
        float(t["value_c"])
        for t in temperatures
        if t.get("source") == source and t.get("value_c") is not None
    ]
    return max(values) if values else None
