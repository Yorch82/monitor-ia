/** Tarjeta KPI de la fila superior. */

import type { ReactNode } from "react";

export function KpiCard({
  icon,
  label,
  value,
  hint,
  footer,
  accent = "cyan",
  progress,
}: {
  icon?: ReactNode;
  label: string;
  value: string;
  hint?: string;
  footer?: ReactNode;
  accent?: "cyan" | "emerald" | "amber" | "red" | "violet" | "blue";
  /** 0-100 opcional para una mini-barra bajo el valor. */
  progress?: number | null;
}) {
  const accents: Record<string, string> = {
    cyan: "from-accent-cyan/70 text-accent-cyan",
    emerald: "from-accent-emerald/70 text-accent-emerald",
    amber: "from-accent-amber/70 text-accent-amber",
    red: "from-accent-red/70 text-accent-red",
    violet: "from-accent-violet/70 text-accent-violet",
    blue: "from-accent-blue/70 text-accent-blue",
  };
  const a = accents[accent] ?? accents.cyan;
  return (
    <div className="card relative overflow-hidden px-4 py-3">
      <div className={`absolute inset-x-0 top-0 h-[2px] bg-gradient-to-r ${a.split(" ")[0]} to-transparent`} />
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="card-title">{label}</div>
          <div className="mt-1 truncate font-mono text-2xl font-semibold tracking-tight text-slate-50">{value}</div>
          {hint && <div className="mt-0.5 truncate text-[11px] text-slate-400">{hint}</div>}
        </div>
        {icon && <span className={`${a.split(" ")[1]} opacity-80`}>{icon}</span>}
      </div>
      {typeof progress === "number" && (
        <div className="mt-2 h-1 w-full overflow-hidden rounded-full bg-white/[0.06]">
          <div
            className={`h-full rounded-full bg-gradient-to-r ${a.split(" ")[0]} to-transparent transition-all duration-500`}
            style={{ width: `${Math.max(0, Math.min(100, progress))}%` }}
          />
        </div>
      )}
      {footer && <div className="mt-2 border-t border-white/[0.05] pt-2 text-[11px] text-slate-400">{footer}</div>}
    </div>
  );
}

export function NoData({ message = "Sin datos" }: { message?: string }) {
  return <span className="text-slate-600">— {message}</span>;
}
