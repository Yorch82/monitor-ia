/** Panel de contexto: barra con semáforo + métricas de la última petición. */

import { useMonitor } from "../../state/MonitorContext";
import { fmtDuration, fmtInt, fmtMs, fmtNum, fmtRelative } from "../../lib/format";
import { Card } from "../ui/Card";
import { ProgressBar } from "../ui/ProgressBar";
import { IconActivity, IconGauge } from "../Icons";

const LEVEL_LABEL: Record<string, string> = {
  ok: "saludable",
  warning: "alto",
  critical: "crítico",
  none: "sin datos",
};

export function ContextCard() {
  const { snapshot } = useMonitor();
  const s = snapshot;
  const ctx = s?.tokens?.context;
  const last = s?.tokens?.last_request;

  const pct = ctx?.percent ?? null;
  const level = ctx?.level ?? "none";

  return (
    <Card title="Ventana de contexto" icon={<IconGauge className="h-4 w-4" />}>
      {ctx?.available ? (
        <>
          <div className="flex items-baseline justify-between gap-2">
            <div className="font-mono text-3xl font-semibold text-slate-50">
              {fmtNum(pct, 1)}
              <span className="text-lg text-slate-500">%</span>
            </div>
            <div
              className={`rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-widest ${
                level === "critical"
                  ? "bg-red-500/15 text-red-300"
                  : level === "warning"
                    ? "bg-amber-500/15 text-amber-300"
                    : "bg-emerald-500/15 text-emerald-300"
              }`}
            >
              {LEVEL_LABEL[level]}
            </div>
          </div>
          <div className="mt-3">
            <ProgressBar percent={pct} level={level} thresholds={[70, 90]} />
            <div className="mt-1.5 flex justify-between text-[11px] text-slate-400">
              <span className="font-mono">{fmtInt(ctx.used_tokens ?? 0)} tokens</span>
              <span className="font-mono">máx {fmtInt(ctx.max_tokens ?? 0)}</span>
            </div>
          </div>
        </>
      ) : (
        <div className="flex h-[104px] flex-col items-center justify-center text-sm text-slate-500">
          <span className="font-mono text-2xl text-slate-700">—</span>
          Sin ocupación de contexto
          <span className="mt-1 text-[11px] text-slate-600">
            (requiere peticiones vía proxy o simulación)
          </span>
        </div>
      )}

      <div className="mt-4 border-t border-white/[0.05] pt-3">
        <div className="card-title mb-2">Última petición</div>
        {last ? (
          <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-xs">
            <Metric label="Input" value={fmtInt(last.input_tokens)} />
            <Metric label="Output" value={fmtInt(last.output_tokens)} />
            <Metric label="Velocidad" value={`${fmtNum(last.tokens_per_second, 1)} t/s`} />
            <Metric label="Duración" value={fmtDuration(last.duration_s)} />
            <Metric label="Modelo" value={last.model ? truncate(last.model, 22) : "—"} />
            <Metric label="Hace" value={fmtRelative(last.ts)} />
          </div>
        ) : (
          <div className="text-xs text-slate-500">Aún no se ha completado ninguna petición.</div>
        )}
        {s?.tokens?.source && s.tokens.source !== "none" && (
          <div className="mt-3 flex items-center gap-2 text-[10px] uppercase tracking-widest text-slate-500">
            <IconActivity className="h-3 w-3" />
            Fuente: {s.tokens.source}
            {s.inference?.latency_ms != null && <> · latencia {fmtMs(s.inference.latency_ms)}</>}
          </div>
        )}
      </div>
    </Card>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-2">
      <span className="text-slate-500">{label}</span>
      <span className="font-mono text-slate-200">{value}</span>
    </div>
  );
}

const truncate = (s: string, n: number) => (s.length > n ? `${s.slice(0, n - 1)}…` : s);
