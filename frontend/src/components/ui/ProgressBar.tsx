/** Barra de progreso de contexto con semáforo (verde <70 %, ámbar 70-90 %, rojo >90 %). */

import type { ContextLevel } from "../../types/telemetry";

const BAR_COLOR: Record<ContextLevel, string> = {
  ok: "bg-accent-emerald",
  warning: "bg-accent-amber",
  critical: "bg-accent-red",
  none: "bg-slate-600",
};

export function ProgressBar({
  percent,
  level,
  thresholds,
}: {
  percent: number | null;
  level: ContextLevel;
  /** Umbrales (pct) para marcar los límites visuales. */
  thresholds?: number[];
}) {
  const width = percent === null ? 0 : Math.max(0, Math.min(100, percent));
  return (
    <div className="relative h-2.5 w-full overflow-hidden rounded-full bg-white/[0.06]">
      <div
        className={`absolute inset-y-0 left-0 rounded-full transition-all duration-500 ${BAR_COLOR[level]}`}
        style={{ width: `${width}%` }}
      />
      {thresholds?.map((t) => (
        <span
          key={t}
          className="absolute inset-y-0 w-px bg-white/25"
          style={{ left: `${Math.min(100, t)}%` }}
        />
      ))}
    </div>
  );
}
