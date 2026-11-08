/** Pestaña Refrigeración: temperaturas, ventiladores, perfiles y control PWM. */

import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import {
  fetchCooling,
  releaseCooling,
  setCoolingFanPwm,
  setCoolingProfile,
} from "../lib/api";
import type {
  CoolingFan,
  CoolingProfile,
  CoolingSnapshot,
  CoolingTemperature,
} from "../types/cooling";
import { fmtNum, fmtRelative } from "../lib/format";
import { Card } from "../components/ui/Card";
import { Gauge } from "../components/ui/Gauge";
import { KpiCard } from "../components/dashboard/KpiCards";
import {
  IconAlert,
  IconCheck,
  IconFan,
  IconFlame,
  IconRefresh,
  IconSnowflake,
  IconThermometer,
  IconWind,
} from "../components/Icons";

const PROFILE_ICON: Record<string, ReactNode> = {
  silent: <IconSnowflake className="h-5 w-5" />,
  balanced: <IconWind className="h-5 w-5" />,
  max: <IconFlame className="h-5 w-5" />,
  auto: <IconThermometer className="h-5 w-5" />,
};

const SOURCE_LABEL: Record<string, string> = {
  cpu: "CPU",
  gpu: "GPU",
  system: "Sistema",
  storage: "Almacenamiento",
};

type Notice = { kind: "ok" | "err"; msg: string } | null;

export function Cooling() {
  const [data, setData] = useState<CoolingSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<Notice>(null);

  const load = useCallback(async () => {
    try {
      setData(await fetchCooling());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo cargar la refrigeración");
    }
  }, []);

  useEffect(() => {
    void load();
    const timer = setInterval(() => void load(), 2000);
    return () => clearInterval(timer);
  }, [load]);

  const canControl = !!data?.control.enabled && !!data?.control.writable;

  const gaugeTemps = useMemo(() => {
    if (!data) return [];
    const preferred: CoolingTemperature[] = [];
    for (const source of ["cpu", "gpu", "system", "storage"] as const) {
      const candidates = data.temperatures.filter((t) => t.source === source);
      if (candidates.length === 0) continue;
      const best = [...candidates].sort((a, b) => b.value_c - a.value_c)[0];
      preferred.push(best);
    }
    return preferred.slice(0, 4);
  }, [data]);

  const applyProfile = async (profile: CoolingProfile) => {
    setBusy(`profile-${profile}`);
    setNotice(null);
    try {
      setData(await setCoolingProfile(profile));
      setNotice({ kind: "ok", msg: "Perfil de refrigeración aplicado." });
    } catch (e) {
      setNotice({ kind: "err", msg: e instanceof Error ? e.message : String(e) });
    } finally {
      setBusy(null);
    }
  };

  const applyFan = async (fan: CoolingFan, pwm: number) => {
    setBusy(`fan-${fan.id}`);
    setNotice(null);
    try {
      setData(await setCoolingFanPwm(fan.id, pwm));
      setNotice({ kind: "ok", msg: `${fan.label}: PWM ajustado al ${pwm} %.` });
    } catch (e) {
      setNotice({ kind: "err", msg: e instanceof Error ? e.message : String(e) });
    } finally {
      setBusy(null);
    }
  };

  const restoreBios = async () => {
    setBusy("release");
    setNotice(null);
    try {
      setData(await releaseCooling());
      setNotice({ kind: "ok", msg: "Control devuelto a la BIOS/EC del servidor." });
    } catch (e) {
      setNotice({ kind: "err", msg: e instanceof Error ? e.message : String(e) });
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="mx-auto max-w-7xl space-y-3 px-4 pb-10 pt-4 sm:px-6">
      <div className="flex flex-wrap items-center justify-between gap-3 px-1">
        <div className="flex items-center gap-2.5">
          <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-accent-cyan/10 text-accent-cyan">
            <IconFan className="h-5 w-5" />
          </span>
          <div>
            <h1 className="text-base font-bold text-slate-50">Refrigeración del servidor</h1>
            <p className="text-[11px] text-slate-500">
              Temperaturas, RPM y control de ventiladores · actualización cada 2 s
            </p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {data && <ModeChip mode={data.mode} />}
          {data && <ControlChip data={data} />}
          {data?.control.emergency_active && (
            <span className="inline-flex items-center gap-1.5 rounded-full border border-red-500/40 bg-red-500/10 px-2.5 py-1 text-[10px] font-bold tracking-wider text-red-300">
              <IconAlert className="h-3 w-3" /> EMERGENCIA TÉRMICA
            </span>
          )}
          <button onClick={() => void load()} className="btn-ghost !px-2.5" title="Actualizar ahora">
            <IconRefresh className={`h-4 w-4 ${busy ? "animate-spin" : ""}`} />
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-2 text-sm text-amber-200">
          {error} — reintentando cada 2 s…
        </div>
      )}
      {notice && (
        <div
          className={`flex items-center gap-2 rounded-xl border px-4 py-2 text-sm ${
            notice.kind === "ok"
              ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-200"
              : "border-red-500/30 bg-red-500/10 text-red-200"
          }`}
        >
          {notice.kind === "ok" ? <IconCheck className="h-4 w-4" /> : <IconAlert className="h-4 w-4" />}
          {notice.msg}
        </div>
      )}

      {data === null ? (
        <Card title="Cargando refrigeración">
          <div className="flex h-40 items-center justify-center gap-2 text-sm text-slate-500">
            <IconFan className="h-5 w-5 animate-spin" /> Consultando sensores del servidor…
          </div>
        </Card>
      ) : (
        <>
          {data.control.emergency_active && (
            <div className="rounded-xl border border-red-500/40 bg-red-500/10 px-4 py-2.5 text-sm text-red-200">
              Protección térmica activa: los ventiladores se han forzado al 100 % hasta bajar de{" "}
              {fmtNum(data.control.emergency_release_c, 0)} ºC.
            </div>
          )}
          {!data.control.enabled && (
            <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-2.5 text-xs leading-relaxed text-amber-200">
              <b>Solo lectura.</b> {data.control.note} Para activar el control en el servidor:
              <code className="ml-1 rounded bg-black/30 px-1">COOLING_CONTROL_ENABLED=true</code> +
              overlay <code className="rounded bg-black/30 px-1">docker-compose.cooling.yml</code> (monta{" "}
              <code className="rounded bg-black/30 px-1">/sys</code> y requiere privilegios).
            </div>
          )}
          {data.control.enabled && data.control.released && (
            <div className="rounded-xl border border-cyan-500/25 bg-cyan-500/[0.06] px-4 py-2.5 text-xs text-cyan-200">
              Control devuelto a la BIOS/EC. Elige un perfil para que Monitor IA vuelva a gestionar los ventiladores.
            </div>
          )}
          {data.control.last_error && (
            <div className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-2 text-xs text-red-200">
              {data.control.last_error}
            </div>
          )}

          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <KpiCard
              label="Temperatura CPU"
              value={data.summary.cpu_temp_c != null ? `${fmtNum(data.summary.cpu_temp_c, 1)} ºC` : "—"}
              hint={data.temperatures.filter((t) => t.source === "cpu").length + " sensores CPU"}
              icon={<IconThermometer className="h-5 w-5" />}
              accent={(data.summary.cpu_temp_c ?? 0) >= 85 ? "red" : (data.summary.cpu_temp_c ?? 0) >= 75 ? "amber" : "emerald"}
              progress={data.summary.cpu_temp_c ?? null}
              footer="verde <75 · ámbar 75-85 · rojo >85"
            />
            <KpiCard
              label="Temperatura GPU"
              value={data.summary.gpu_temp_c != null ? `${fmtNum(data.summary.gpu_temp_c, 1)} ºC` : "—"}
              hint={data.temperatures.filter((t) => t.source === "gpu").length + " sensores GPU"}
              icon={<IconThermometer className="h-5 w-5" />}
              accent={(data.summary.gpu_temp_c ?? 0) >= 83 ? "red" : (data.summary.gpu_temp_c ?? 0) >= 75 ? "amber" : "violet"}
              progress={data.summary.gpu_temp_c ?? null}
              footer={`emergencia ${fmtNum(data.control.emergency_temp_c, 0)} ºC`}
            />
            <KpiCard
              label="Máximo"
              value={data.summary.max_temp_c != null ? `${fmtNum(data.summary.max_temp_c, 1)} ºC` : "—"}
              hint={`emergencia a ${fmtNum(data.control.emergency_temp_c, 0)} ºC`}
              icon={<IconFlame className="h-5 w-5" />}
              accent={data.control.emergency_active ? "red" : "cyan"}
              progress={data.summary.max_temp_c ?? null}
              footer={data.control.emergency_active ? "ventiladores forzados al 100 %" : "CPU/GPU más caliente"}
            />
            <KpiCard
              label="Ventiladores"
              value={data.summary.avg_fan_rpm != null ? `${fmtNum(data.summary.avg_fan_rpm, 0)} RPM` : "—"}
              hint={`${data.summary.fan_count} ventiladores · ${data.summary.controllable_fans} controlables`}
              icon={<IconFan className="h-5 w-5" />}
              accent="amber"
              footer={`actualizado ${fmtRelative(data.updated_at)}`}
            />
          </div>

          <Card title="Perfiles de refrigeración" icon={<IconSnowflake className="h-4 w-4" />}>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
              {data.profiles.map((profile) => {
                const active = !data.control.released && data.control.profile === profile.id;
                const disabled = !canControl || busy !== null;
                return (
                  <button
                    key={profile.id}
                    onClick={() => void applyProfile(profile.id)}
                    disabled={disabled}
                    className={`relative rounded-2xl border p-4 text-left transition ${
                      active
                        ? "border-accent-cyan/50 bg-accent-cyan/[0.07] shadow-glow"
                        : "border-white/[0.07] bg-white/[0.02] hover:border-white/20 hover:bg-white/[0.04]"
                    } ${disabled ? "cursor-not-allowed opacity-50" : ""}`}
                  >
                    <div className="flex items-start justify-between">
                      <span className={active ? "text-accent-cyan" : "text-slate-400"}>
                        {PROFILE_ICON[profile.id]}
                      </span>
                      {active && (
                        <span className="rounded-full bg-accent-cyan/15 px-2 py-0.5 text-[9px] font-bold uppercase tracking-wider text-accent-cyan">
                          activo
                        </span>
                      )}
                      {busy === `profile-${profile.id}` && (
                        <span className="h-3 w-3 animate-spin rounded-full border border-white/30 border-t-white" />
                      )}
                    </div>
                    <div className="mt-3 text-sm font-semibold text-slate-100">{profile.label}</div>
                    <div className="mt-0.5 text-[11px] text-slate-400">{profile.description}</div>
                    <div className="mt-2 font-mono text-[10px] text-slate-500">
                      {profile.target_pwm_pct != null ? `${profile.target_pwm_pct}% PWM` : "curva 25–100%"}
                    </div>
                    {!active && canControl && (
                      <div className="mt-2 text-[9px] uppercase tracking-wider text-slate-600">
                        Pulsa para activar
                      </div>
                    )}
                  </button>
                );
              })}
            </div>
            <p className="mt-3 text-[10px] leading-relaxed text-slate-600">
              Perfil silencioso recomendado en invierno · perfil máximo en verano. Si el control está
              desactivado o no hay canales PWM, los perfiles aparecen deshabilitados y solo se monitoriza.
            </p>
          </Card>

          <div className="grid grid-cols-1 gap-3 xl:grid-cols-3">
            <Card title="Temperaturas" icon={<IconThermometer className="h-4 w-4" />} className="xl:col-span-2">
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                {gaugeTemps.map((temp) => (
                  <TempGauge key={temp.id} temp={temp} />
                ))}
              </div>
              <div className="mt-4 border-t border-white/[0.05] pt-3">
                <div className="card-title mb-2">Todos los sensores</div>
                <div className="flex flex-wrap gap-1.5">
                  {data.temperatures.map((temp) => (
                    <span
                      key={temp.id}
                      className="inline-flex items-center gap-1.5 rounded-md border border-white/[0.06] bg-white/[0.02] px-2 py-1 text-[10px] text-slate-400"
                    >
                      <span className="uppercase tracking-wider text-slate-600">{SOURCE_LABEL[temp.source] ?? temp.source}</span>
                      {temp.label}
                      <span className="font-mono text-slate-200">{fmtNum(temp.value_c, 1)} ºC</span>
                    </span>
                  ))}
                  {data.temperatures.length === 0 && (
                    <span className="text-xs text-slate-500">Sin sensores de temperatura accesibles.</span>
                  )}
                </div>
              </div>
            </Card>

            <Card title="Control y seguridad" icon={<IconFan className="h-4 w-4" />}>
              <div className="space-y-2 text-xs">
                <SafetyRow label="PWM mínimo" value={`${fmtNum(data.control.min_pwm_pct, 0)} %`} />
                <SafetyRow label="Emergencia" value={`≥ ${fmtNum(data.control.emergency_temp_c, 0)} ºC → 100 %`} />
                <SafetyRow label="Liberar emergencia" value={`≤ ${fmtNum(data.control.emergency_release_c, 0)} ºC`} />
                <SafetyRow label="Restaurar al salir" value={data.control.restore_on_exit ? "Sí (BIOS)" : "No"} />
                <SafetyRow
                  label="Estado"
                  value={
                    data.control.emergency_active
                      ? "Protección térmica"
                      : data.control.released
                        ? "Control BIOS"
                        : data.control.enabled && data.control.writable
                          ? "Control activo"
                          : "Solo lectura"
                  }
                />
              </div>
              <div className="mt-4 space-y-2">
                <button
                  onClick={() => void applyProfile("max")}
                  disabled={!canControl || busy !== null}
                  className="btn-primary w-full justify-center"
                >
                  <IconFlame className="h-4 w-4" /> Ventilación máxima ahora
                </button>
                <button
                  onClick={() => void restoreBios()}
                  disabled={!canControl || busy !== null}
                  className="btn-ghost w-full justify-center"
                >
                  <IconRefresh className="h-4 w-4" /> Restaurar control BIOS
                </button>
              </div>
              <div className="mt-3 text-[10px] leading-relaxed text-slate-600">
                {data.control.note}
              </div>
            </Card>
          </div>

          <Card title="Ventiladores" icon={<IconFan className="h-4 w-4" />}>
            {data.fans.length === 0 ? (
              <div className="py-8 text-center text-sm text-slate-500">
                No se han encontrado ventiladores accesibles. Monta <code className="rounded bg-black/30 px-1">/sys</code> en el backend.
              </div>
            ) : (
              <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
                {data.fans.map((fan) => (
                  <FanCard
                    key={fan.id}
                    fan={fan}
                    canControl={canControl}
                    busy={busy === `fan-${fan.id}`}
                    onApply={(pwm) => void applyFan(fan, pwm)}
                  />
                ))}
              </div>
            )}
          </Card>

          <p className="px-1 text-[10px] leading-relaxed text-slate-600">
            El control de refrigeración escribe en <code className="rounded bg-black/30 px-1">/sys/class/hwmon</code> y,
            si está activado, en los ventiladores NVIDIA vía NVML. Mínimo de seguridad{" "}
            {fmtNum(data.control.min_pwm_pct, 0)} % · emergencia {fmtNum(data.control.emergency_temp_c, 0)} ºC.
            El historial de perfiles se guarda en SQLite y se aplica al arrancar si el control está habilitado.
          </p>
        </>
      )}
    </div>
  );
}

function ModeChip({ mode }: { mode: "simulation" | "live" }) {
  const sim = mode === "simulation";
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[10px] font-bold tracking-wider ${
        sim
          ? "border-violet-500/40 bg-violet-500/10 text-violet-300"
          : "border-emerald-500/40 bg-emerald-500/10 text-emerald-300"
      }`}
    >
      {sim ? "SIMULACIÓN" : "LIVE"}
    </span>
  );
}

function ControlChip({ data }: { data: CoolingSnapshot }) {
  const state = data.control.emergency_active
    ? { label: "EMERGENCIA", cls: "border-red-500/40 bg-red-500/10 text-red-300" }
    : data.control.released
      ? { label: "CONTROL BIOS", cls: "border-cyan-500/30 bg-cyan-500/10 text-cyan-300" }
      : data.control.enabled && data.control.writable
        ? { label: "CONTROL ACTIVO", cls: "border-emerald-500/30 bg-emerald-500/10 text-emerald-300" }
        : { label: "SOLO LECTURA", cls: "border-amber-500/30 bg-amber-500/10 text-amber-300" };
  return (
    <span className={`inline-flex items-center rounded-full border px-2.5 py-1 text-[10px] font-bold tracking-wider ${state.cls}`}>
      {state.label}
    </span>
  );
}

function TempGauge({ temp }: { temp: CoolingTemperature }) {
  const warn = temp.source === "gpu" ? 75 : 75;
  const crit = temp.source === "gpu" ? 83 : 85;
  return (
    <div className="flex flex-col items-center rounded-xl border border-white/[0.05] bg-white/[0.02] px-2 py-3">
      <Gauge
        value={temp.value_c}
        display={`${fmtNum(temp.value_c, 1)} ºC`}
        label={SOURCE_LABEL[temp.source] ?? temp.source}
        size={104}
        warn={warn}
        crit={crit}
      />
      <div className="mt-1 line-clamp-2 text-center text-[10px] text-slate-500">{temp.label}</div>
    </div>
  );
}

function FanCard({
  fan,
  canControl,
  busy,
  onApply,
}: {
  fan: CoolingFan;
  canControl: boolean;
  busy: boolean;
  onApply: (pwm: number) => void;
}) {
  const initial = fan.pwm_pct ?? Math.round(fan.min_pwm_pct);
  const [pwm, setPwm] = useState(initial);

  useEffect(() => {
    setPwm(fan.pwm_pct ?? initial);
  }, [fan.pwm_pct, initial]);

  const enabled = canControl && fan.controllable;
  return (
    <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-4">
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className={fan.kind === "gpu" ? "text-accent-violet" : "text-accent-cyan"}>
            <IconFan className="h-4 w-4" />
          </span>
          <div>
            <div className="text-xs font-semibold text-slate-200">{fan.label}</div>
            <div className="text-[9px] uppercase tracking-widest text-slate-500">
              {fan.kind === "gpu" ? "GPU · " : "Sistema · "}
              {fan.is_protected ? "bomba protegida" : fan.controllable ? "controlable" : "solo lectura"}
            </div>
          </div>
        </div>
        <div className="text-right">
          <div className="font-mono text-sm text-slate-100">{fan.rpm != null ? `${fmtNum(fan.rpm, 0)} RPM` : "— RPM"}</div>
          <div className="text-[9px] text-slate-500">actual</div>
        </div>
      </div>

      <div className="mt-3 flex items-center justify-between text-[10px] text-slate-500">
        <span>PWM</span>
        <span className="font-mono text-slate-300">
          {fan.pwm_pct != null ? `${fmtNum(fan.pwm_pct, 0)} %` : "—"}
          {enabled ? ` → ${pwm} %` : ""}
        </span>
      </div>
      <input
        type="range"
        min={Math.round(fan.min_pwm_pct)}
        max={100}
        step={1}
        value={pwm}
        disabled={!enabled || busy}
        onChange={(e) => setPwm(Number(e.target.value))}
        className="mt-1 h-1.5 w-full cursor-pointer accent-cyan-400 disabled:cursor-not-allowed disabled:opacity-40"
      />
      <div className="mt-1 flex justify-between text-[9px] text-slate-600">
        <span>{fmtNum(fan.min_pwm_pct, 0)} % mín.</span>
        <span>100 %</span>
      </div>
      {fan.last_error && <div className="mt-2 text-[9px] text-red-300">{fan.last_error}</div>}
      {enabled ? (
        <button
          onClick={() => onApply(pwm)}
          disabled={busy || pwm === fan.pwm_pct}
          className="btn-ghost mt-3 w-full justify-center !py-1.5 !text-[11px]"
        >
          {busy ? "Aplicando…" : "Aplicar ventilador"}
        </button>
      ) : (
        <div className="mt-3 text-center text-[9px] text-amber-300/80">
          {fan.is_protected
            ? "Protegido: control gestionado por la BIOS"
            : !canControl
              ? "Activa el control para editar"
              : "Sin canal PWM escribible"}
        </div>
      )}
    </div>
  );
}

function SafetyRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-2">
      <span className="text-slate-500">{label}</span>
      <span className="font-mono text-[11px] text-slate-300">{value}</span>
    </div>
  );
}
