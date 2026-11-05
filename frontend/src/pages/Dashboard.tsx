/** Página principal: KPIs + gráficas + hardware + coste. */

import { useMonitor } from "../state/MonitorContext";
import { KpiRow } from "../components/dashboard/KpiRow";
import { ContextCard } from "../components/dashboard/ContextCard";
import { HardwareRow } from "../components/dashboard/HardwareRow";
import { CostCard } from "../components/dashboard/CostCard";
import { PowerChart, ResourcesChart, TokensChart } from "../components/charts/Charts";
import { fmtUptime } from "../lib/format";

export function Dashboard() {
  const { snapshot, lastError } = useMonitor();
  const s = snapshot;

  return (
    <div className="mx-auto max-w-7xl space-y-3 px-4 pb-10 pt-4 sm:px-6">
      {lastError && (
        <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-2 text-sm text-amber-200">
          {lastError} — reintentando automáticamente…
        </div>
      )}

      {s === null ? (
        <SkeletonState />
      ) : (
        <>
          <div className="flex items-center justify-between px-1 text-[11px] uppercase tracking-widest text-slate-500">
            <span>
              intervalo {s.interval_s}s · modo {s.mode === "simulation" ? "simulación" : "live"} ·
              uptime {fmtUptime((s.system?.uptime_s as number | null) ?? null)}
            </span>
            {s.inference && s.inference.status !== "online" && s.mode === "live" && (
              <span className="text-red-300">inference: {s.inference.error ?? s.inference.status}</span>
            )}
          </div>
          <KpiRow />
          <div className="grid grid-cols-1 gap-3 xl:grid-cols-3">
            <div className="xl:col-span-2">
              <TokensChart />
            </div>
            <ContextCard />
          </div>
          <HardwareRow />
          <div className="grid grid-cols-1 gap-3 xl:grid-cols-3">
            <div className="xl:col-span-2">
              <ResourcesChart />
            </div>
            <CostCard />
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
            <div className="lg:col-span-2">
              <PowerChart />
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function SkeletonState() {
  return (
    <div className="flex h-[60vh] flex-col items-center justify-center gap-3 text-slate-500">
      <div className="h-10 w-10 animate-live-pulse rounded-xl bg-accent-cyan/20" />
      <div className="text-sm">Esperando el primer frame de telemetría…</div>
      <div className="text-[11px] text-slate-600">Comprueba que el backend está activo.</div>
    </div>
  );
}
