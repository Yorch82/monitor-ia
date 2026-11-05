/** Tarjetas de hardware: una por GPU (gauge), potencia y RAM con gauges circulares. */

import { useMonitor } from "../../state/MonitorContext";
import { fmtGb, fmtNum } from "../../lib/format";
import { Gauge } from "../ui/Gauge";
import { ProgressBar } from "../ui/ProgressBar";
import { IconBolt, IconCpu, IconMemory, IconServer } from "../Icons";

function GpuCard({ g }: { g: NonNullable<ReturnType<typeof useMonitor>["snapshot"]>["gpus"][number] }) {  const util = g.utilization_pct;
  const vramPct = g.memory_pct;
  const nb = (v: number | null, unit = "", d = 0) => (v == null ? "—" : `${fmtNum(v, d)}${unit}`);
  return (
    <div className="card flex flex-col gap-3 px-4 py-4">
      <div className="flex items-center gap-2">
        <span className="text-accent-violet">
          <IconServer className="h-4 w-4" />
        </span>
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold text-slate-100">{g.name}</div>
          <div className="text-[10px] uppercase tracking-widest text-slate-500">
            GPU {g.index} · {g.vendor}
          </div>
        </div>
      </div>
      <div className="flex items-center gap-4">
        <Gauge value={util} label="uso" size={116} />
        <div className="flex-1 space-y-2.5 text-xs">
          <div>
            <div className="mb-1 flex justify-between text-slate-400">
              <span>VRAM</span>
              <span className="font-mono text-slate-200">
                {fmtGb(g.memory_used_mb)} / {fmtGb(g.memory_total_mb)}
              </span>
            </div>
            <ProgressBar percent={vramPct} level={vramPct == null ? "none" : vramPct > 95 ? "critical" : vramPct >= 70 ? "warning" : "ok"} thresholds={[70, 95]} />
          </div>
          <Row label="Temperatura" value={nb(g.temperature_c, " ºC")} hot={g.temperature_c != null && g.temperature_c >= 80} />
          <Row label="Ventilador" value={nb(g.fan_pct, " %")} />
          <Row label="Potencia" value={`${nb(g.power_w, " W", 0)} de ${nb(g.power_limit_w, " W", 0)}`} hot={g.power_pct != null && g.power_pct > 95} />
        </div>
      </div>
      {(util == null && vramPct == null) && (
        <div className="text-center text-[11px] text-amber-400/80">Sin datos de esta GPU</div>
      )}
    </div>
  );
}

function Row({ label, value, hot }: { label: string; value: string; hot?: boolean }) {
  return (
    <div className="flex items-center justify-between gap-2">
      <span className="text-slate-500">{label}</span>
      <span className={`font-mono ${hot ? "text-red-300" : "text-slate-200"}`}>{value}</span>
    </div>
  );
}

export function HardwareRow() {
  const { snapshot } = useMonitor();
  const s = snapshot;
  const power = s?.power;
  const system = s?.system;
  const powerPct = power?.percent ?? null;

  return (
    <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
      {/* GPUs reales (una tarjeta por GPU) */}
      {(s?.gpus ?? []).map((g) => (
        <GpuCard key={g.index} g={g} />
      ))}

      {/* Sin GPU disponible */}
      {s && s.gpus.length === 0 && (
        <div className="card flex flex-col items-center justify-center gap-2 px-4 py-8 text-center">
          <span className="text-slate-600">
            <IconCpu className="h-6 w-6" />
          </span>
          <div className="text-sm font-semibold text-slate-300">GPU sin datos</div>
          <div className="max-w-xs text-[11px] leading-relaxed text-slate-500">
            {s.hardware?.gpu_error ?? "No hay proveedor de GPU disponible en este servidor."}
          </div>
        </div>
      )}

      {/* Potencia (gauge + energía y coste de sesión) */}
      <div className="card flex flex-col gap-3 px-4 py-4">
        <div className="flex items-center gap-2">
          <span className="text-accent-amber">
            <IconBolt className="h-4 w-4" />
          </span>
          <div>
            <div className="text-sm font-semibold text-slate-100">Potencia eléctrica</div>
            <div className="text-[10px] uppercase tracking-widest text-slate-500">suma de GPUs</div>
          </div>
        </div>
        <div className="flex items-center gap-4">
          <Gauge value={powerPct} label="TDP" size={116} />
          <div className="flex-1 space-y-2 text-xs">
            <Row label="Consumo" value={power?.current_w != null ? `${fmtNum(power.current_w, 0)} W` : "—"} />
            <Row label="Límite" value={power?.limit_w != null ? `${fmtNum(power.limit_w, 0)} W` : "—"} />
            <Row label="Energía sesión" value={power?.energy_session_wh != null ? `${fmtNum(power.energy_session_wh, 0)} Wh` : "—"} />
            <Row label="Energía (kWh)" value={power?.energy_session_kwh != null ? `${fmtNum(power.energy_session_kwh, 3)} kWh` : "—"} />
          </div>
        </div>
        {power?.available === false && (
          <div className="text-center text-[11px] text-amber-400/80">
            Sin datos de potencia (¿GPU sin sensor?)
          </div>
        )}
      </div>

      {/* RAM + CPU */}
      <div className="card flex flex-col gap-3 px-4 py-4">
        <div className="flex items-center gap-2">
          <span className="text-accent-cyan">
            <IconMemory className="h-4 w-4" />
          </span>
          <div>
            <div className="text-sm font-semibold text-slate-100">RAM del sistema</div>
            <div className="text-[10px] uppercase tracking-widest text-slate-500">{system?.cpu_count ? `${system.cpu_count} hilos` : ""}</div>
          </div>
        </div>
        <div className="flex items-center gap-4">
          <Gauge value={system?.ram_pct ?? null} label="RAM" size={116} />
          <div className="flex-1 space-y-2 text-xs">
            <Row label="Usada" value={system?.ram_used_gb != null ? `${fmtNum(system.ram_used_gb, 1)} GB` : "—"} />
            <Row label="Total" value={system?.ram_total_gb != null ? `${fmtNum(system.ram_total_gb, 1)} GB` : "—"} />
            <Row label="CPU" value={system?.cpu_pct != null ? `${fmtNum(system.cpu_pct, 0)} %` : "—"} />
            <Row label="Swap" value={system?.swap_pct ? `${fmtNum(system.swap_pct, 0)} %` : "—"} />
          </div>
        </div>
      </div>
    </div>
  );
}
