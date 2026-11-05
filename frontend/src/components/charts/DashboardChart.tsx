/** Gráficas Recharts con estilos del tema (tooltip/grid oscuros) y selector de rango. */

import { useMemo } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceArea,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { ChartPoint, Range } from "../../types/telemetry";
import { fmtNum, fmtTime } from "../../lib/format";
import { RANGES, rangeLabel } from "../../lib/points";

export interface SeriesDef {
  key: keyof ChartPoint;
  label: string;
  color: string;
  dashed?: boolean;
}

export interface Thresholds {
  warn?: number;
  crit?: number;
}

function DarkTooltip({ active, payload, range }: { active?: boolean; payload?: Array<{ name: string; value: number; color: string; payload?: unknown }>; range: Range }) {
  if (!active || !payload?.length) return null;
  const t = payload[0]?.payload as ChartPoint | undefined;
  return (
    <div className="rounded-lg border border-white/10 bg-ink-900/95 px-3 py-2 text-xs shadow-card backdrop-blur">
      <div className="mb-1 font-semibold text-slate-300">{t ? fmtTime(t.t, range) : ""}</div>
      {payload.map((p) => (
        <div key={p.name} className="flex items-center justify-between gap-4">
          <span className="flex items-center gap-1.5 text-slate-400">
            <span className="h-1.5 w-1.5 rounded-full" style={{ background: p.color }} />
            {p.name}
          </span>
          <span className="font-mono text-slate-100">
            {fmtNum(p.value, 2)}
            {!Number.isNaN(Number(p.value)) && p.value != null ? "" : ""}
          </span>
        </div>
      ))}
    </div>
  );
}

export function RangeSelector({ range, onChange }: { range: Range; onChange: (r: Range) => void }) {
  return (
    <div className="flex items-center gap-1 rounded-lg border border-white/10 bg-white/[0.03] p-0.5">
      {RANGES.map((r) => (
        <button
          key={r}
          onClick={() => onChange(r)}
          title={rangeLabel(r)}
          className={`rounded-md px-2 py-1 text-[11px] font-semibold tracking-wide transition ${
            r === range ? "bg-accent-cyan/90 text-ink-950" : "text-slate-400 hover:text-slate-200"
          }`}
        >
          {r.toUpperCase()}
        </button>
      ))}
    </div>
  );
}

export function DashboardChart({
  points,
  range,
  series,
  yDomain,
  onRangeChange,
  thresholds,
  unitSuffix,
}: {
  points: ChartPoint[];
  range: Range;
  series: SeriesDef[];
  yDomain?: [string | number, string | number];
  onRangeChange: (r: Range) => void;
  thresholds?: Thresholds;
  unitSuffix?: string;
}) {
  const domain = useMemo<[string, string]>(() => (yDomain as [string, string]) ?? ["0", "auto"], [yDomain]);

  return (
    <div>
      <div className="h-[240px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={points} margin={{ top: 6, right: 8, bottom: 0, left: 0 }}>
            <CartesianGrid stroke="rgba(255,255,255,0.05)" vertical={false} />
            <XAxis
              dataKey="t"
              tickFormatter={(v) => fmtTime(v as number, range)}
              tick={{ fill: "#64748b", fontSize: 10 }}
              axisLine={false}
              tickLine={false}
              minTickGap={48}
            />
            <YAxis
              domain={domain}
              tick={{ fill: "#64748b", fontSize: 10 }}
              axisLine={false}
              tickLine={false}
              width={38}
              unit={unitSuffix}
            />
            <Tooltip content={<DarkTooltip range={range} />} />
            {thresholds?.warn !== undefined && (
              <ReferenceArea y1={thresholds.warn} y2={thresholds.crit ?? 100} fill="rgba(251,191,36,0.05)" ifOverflow="extendDomain" />
            )}
            {thresholds?.crit !== undefined && (
              <ReferenceArea y1={thresholds.crit} y2="auto" ifOverflow="extendDomain" fill="rgba(248,113,113,0.06)" />
            )}
            {series.map((s) => (
              <Line
                key={String(s.key)}
                type="monotone"
                dataKey={s.key as string}
                name={s.label}
                stroke={s.color}
                strokeWidth={1.8}
                strokeDasharray={s.dashed ? "5 4" : undefined}
                dot={false}
                isAnimationActive={false}
                connectNulls
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
      <div className="mt-1 flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap gap-x-4 gap-y-1 text-[11px]">
          {series.map((s) => (
            <span key={String(s.key)} className="flex items-center gap-1.5 text-slate-400">
              <span className="h-1.5 w-3 rounded-full" style={{ background: s.color }} />
              {s.label}
            </span>
          ))}
        </div>
        <RangeSelector range={range} onChange={onRangeChange} />
      </div>
    </div>
  );
}
