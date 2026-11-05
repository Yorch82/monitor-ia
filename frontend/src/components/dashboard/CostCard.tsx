/** Panel de coste energético: coste sesión, proyecciones y coste por 1000 tokens. */

import { useMonitor } from "../../state/MonitorContext";
import { fmtEur, fmtNum } from "../../lib/format";
import { Card } from "../ui/Card";
import { ProgressBar } from "../ui/ProgressBar";
import { IconEuro } from "../Icons";

export function CostCard() {
  const { snapshot } = useMonitor();
  const cost = snapshot?.cost;
  if (!cost) return null;

  const dailyLimit = cost.daily_limit ?? 0;
  const dailyPct = cost.daily_pct ?? null;
  const overLimit = dailyLimit > 0 && cost.daily_cost > dailyLimit;

  return (
    <Card title="Coste energético" icon={<IconEuro className="h-4 w-4" />}>
      <div className="grid grid-cols-2 gap-3">
        <Stat label="Sesión" value={fmtEur(cost.session_cost, 3)} hint={`${fmtNum(((cost.session_cost / Math.max(cost.price_per_kwh, 1e-9)) * 1000), 2)} kWh`} />
        <Stat label="Hoy" value={fmtEur(cost.daily_cost, 2)} hint={`precio ${fmtNum(cost.price_per_kwh, 3)} €/kWh`} />
      </div>

      <div className="mt-4">
        <div className="card-title mb-2">Proyección al ritmo actual</div>
        <div className="grid grid-cols-3 gap-2 text-center">
          <ProjBox label="Por hora" value={fmtEur(cost.cost_per_hour, 2)} />
          <ProjBox label="Por día" value={fmtEur(cost.projection_day, 2)} />
          <ProjBox label="Por mes" value={fmtEur(cost.projection_month, 2)} />
        </div>
      </div>

      <div className="mt-4 flex items-center justify-between text-xs">
        <span className="text-slate-400">Coste / 1.000 tokens generados</span>
        <span className="font-mono text-base font-semibold text-slate-50">{fmtEur(cost.cost_per_1k_tokens, 4)}</span>
      </div>

      {dailyLimit > 0 && (
        <div className="mt-4 border-t border-white/[0.05] pt-3">
          <div className="mb-1.5 flex items-center justify-between text-[11px]">
            <span className="text-slate-400">
              Presupuesto diario · límite {fmtEur(dailyLimit, 2)}
            </span>
            <span className={`font-mono ${overLimit ? "text-red-300" : "text-slate-300"}`}>
              {fmtNum(dailyPct, 0)}%
            </span>
          </div>
          <ProgressBar
            percent={dailyPct}
            level={
              dailyPct != null
                ? dailyPct > 100
                  ? "critical"
                  : dailyPct >= 90
                    ? "warning"
                    : "ok"
                : "none"
            }
          />
        </div>
      )}
    </Card>
  );
}

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] px-3 py-2.5">
      <div className="text-[10px] uppercase tracking-widest text-slate-500">{label}</div>
      <div className="mt-0.5 font-mono text-xl font-semibold text-slate-50">{value}</div>
      {hint && <div className="mt-0.5 text-[10px] text-slate-500">{hint}</div>}
    </div>
  );
}

function ProjBox({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-white/[0.06] bg-white/[0.02] px-2 py-2">
      <div className="text-[9px] uppercase tracking-widest text-slate-500">{label}</div>
      <div className="mt-0.5 font-mono text-sm font-semibold text-slate-100">{value}</div>
    </div>
  );
}
