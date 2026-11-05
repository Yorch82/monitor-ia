/** Gauge circular SVG con color semántico (verde/ámbar/rojo). */

import { fmtNum } from "../../lib/format";

const COLOR: Record<string, string> = {
  ok: "#34d399",
  warning: "#fbbf24",
  critical: "#f87171",
  none: "#64748b",
};

export function levelOf(pct: number | null | undefined, warn = 70, crit = 90): "ok" | "warning" | "critical" | "none" {
  if (pct === null || pct === undefined || Number.isNaN(pct)) return "none";
  if (pct > crit) return "critical";
  if (pct >= warn) return "warning";
  return "ok";
}

export function Gauge({
  value,
  display,
  sublabel,
  warn = 70,
  crit = 90,
  size = 132,
  label,
}: {
  value: number | null;
  display?: string;
  sublabel?: string;
  warn?: number;
  crit?: number;
  size?: number;
  label?: string;
}) {
  const level = levelOf(value, warn, crit);
  const color = COLOR[level];
  const pct = value === null ? 0 : Math.max(0, Math.min(100, value));
  const r = 52;
  const c = 2 * Math.PI * r;
  const offset = c * (1 - pct / 100);

  return (
    <div className="flex flex-col items-center gap-1.5" style={{ width: size }}>
      <svg width={size} height={size} viewBox="0 0 120 120" className="-rotate-90">
        <circle cx="60" cy="60" r={r} stroke="rgba(255,255,255,0.07)" strokeWidth="9" fill="none" />
        <circle
          cx="60"
          cy="60"
          r={r}
          stroke={color}
          strokeWidth="9"
          strokeLinecap="round"
          fill="none"
          strokeDasharray={c}
          strokeDashoffset={offset}
          style={{
            transition: "stroke-dashoffset 0.6s ease, stroke 0.4s ease",
            filter: level !== "none" ? `drop-shadow(0 0 6px ${color}55)` : undefined,
          }}
        />
      </svg>
      <div className="-mt-[86px] mb-[52px] flex flex-col items-center">
        <span className="font-mono text-2xl font-semibold tracking-tight text-slate-50">
          {display ?? fmtNum(value, 1) + "%"}
        </span>
        {label && <span className="text-[10px] uppercase tracking-widest text-slate-500">{label}</span>}
      </div>
      {sublabel && <span className="text-center text-xs text-slate-400">{sublabel}</span>}
    </div>
  );
}
