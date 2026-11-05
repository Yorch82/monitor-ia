/** Fila superior de KPIs: tokens/s, contexto, GPU, potencia, €/h y RAM. */

import { useMonitor } from "../../state/MonitorContext";
import { fmtEur, fmtInt, fmtNum } from "../../lib/format";
import { IconActivity, IconBolt, IconCpu, IconEuro, IconGauge, IconMemory } from "../Icons";
import { KpiCard } from "./KpiCards";

const NONE = "—";

export function KpiRow() {
  const { snapshot: s } = useMonitor();

  const tokens = s?.tokens;
  const context = tokens?.context;
  const power = s?.power;
  const cost = s?.cost;
  const system = s?.system;

  const gpuAvg = s?.gpu_avg_pct ?? null;
  const ramPct = system?.ram_pct ?? null;
  const vramAvg = s?.vram_avg_pct ?? null;

  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
      <KpiCard
        label="Tokens/s"
        value={tokens ? fmtNum(tokens.instant_output_per_s, 1) : NONE}
        hint={tokens ? `media móvil ${fmtNum(tokens.moving_avg_output_per_s, 1)} · entrada ${fmtNum(tokens.instant_input_per_s, 1)}` : undefined}
        icon={<IconActivity className="h-5 w-5" />}
        accent="emerald"
        footer={
          tokens?.last_request ? (
            <span>
              Última petición: {fmtNum(tokens.last_request.tokens_per_second, 1)} t/s ({fmtInt(tokens.last_request.total_tokens)} tokens)
            </span>
          ) : tokens?.source === "none" ? (
            <span className="text-slate-500">Sin tráfico de tokens</span>
          ) : null
        }
      />
      <KpiCard
        label="Contexto"
        value={context?.available ? `${fmtNum(context.percent, 1)}%` : NONE}
        hint={context?.available ? `${fmtInt(context.used_tokens ?? 0)} / ${fmtInt(context.max_tokens ?? 0)} tokens` : "Sin datos"}
        icon={<IconGauge className="h-5 w-5" />}
        accent={context?.level === "critical" ? "red" : context?.level === "warning" ? "amber" : "cyan"}
        progress={context?.percent ?? null}
        footer={context?.available ? <span>origen: {context.source}</span> : null}
      />
      <KpiCard
        label="GPU"
        value={gpuAvg !== null ? `${fmtNum(gpuAvg, 0)}%` : NONE}
        hint={
          s?.gpus?.length
            ? `${s.gpus.length} GPU(s) · ${fmtNum(s.gpu_temp_max_c, 0)} ºC`
            : s?.hardware?.gpu_error ?? "Sin GPU detectada"
        }
        icon={<IconCpu className="h-5 w-5" />}
        accent={gpuAvg !== null && gpuAvg > 90 ? "red" : gpuAvg !== null && gpuAvg >= 70 ? "amber" : "violet"}
        progress={gpuAvg}
        footer={vramAvg !== null ? <span>VRAM {fmtNum(vramAvg, 0)}%</span> : null}
      />
      <KpiCard
        label="Potencia"
        value={power?.current_w != null ? `${fmtNum(power.current_w, 0)} W` : NONE}
        hint={
          power?.limit_w
            ? `límite ${fmtNum(power.limit_w, 0)} W · ${fmtNum(power.percent, 0)}% TDP`
            : power?.available === false
              ? "Sin datos de potencia"
              : undefined
        }
        icon={<IconBolt className="h-5 w-5" />}
        accent="amber"
        progress={power?.percent ?? null}
        footer={power?.available ? <span>sesión {fmtNum((power.energy_session_wh ?? 0) / 1000, 2)} kWh</span> : null}
      />
      <KpiCard
        label="Coste €/h"
        value={cost?.cost_per_hour != null ? fmtEur(cost.cost_per_hour, 2) : NONE}
        hint={cost ? `día proy. ${fmtEur(cost.projection_day, 2)} · mes ${fmtEur(cost.projection_month, 2)}` : undefined}
        icon={<IconEuro className="h-5 w-5" />}
        accent="blue"
        footer={cost ? <span>sesión {fmtEur(cost.session_cost, 3)} · hoy {fmtEur(cost.daily_cost, 2)}</span> : null}
      />
      <KpiCard
        label="RAM"
        value={ramPct != null ? `${fmtNum(ramPct, 0)}%` : NONE}
        hint={system?.ram_used_gb != null ? `${fmtNum(system.ram_used_gb, 1)} / ${fmtNum(system.ram_total_gb, 1)} GB` : undefined}
        icon={<IconMemory className="h-5 w-5" />}
        accent={ramPct != null && ramPct > 90 ? "red" : ramPct != null && ramPct >= 70 ? "amber" : "cyan"}
        progress={ramPct}
        footer={system?.cpu_pct != null ? <span>CPU {fmtNum(system.cpu_pct, 0)}%</span> : null}
      />
    </div>
  );
}
