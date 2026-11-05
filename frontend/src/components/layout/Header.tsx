/** Cabecera global: marca, navegación, estado de conexión, modo y export CSV. */

import { NavLink } from "react-router-dom";
import { useMonitor } from "../../state/MonitorContext";
import { exportCsvUrl } from "../../lib/api";
import type { Range } from "../../types/telemetry";
import { IconActivity, IconDownload, IconSettings, IconShield } from "../Icons";
import { RANGES } from "../../lib/points";

function ConnectionBadge() {
  const { connection } = useMonitor();
  const map = {
    live: { text: "EN VIVO", cls: "text-accent-emerald", dot: "bg-accent-emerald animate-live-pulse" },
    connecting: { text: "CONECTANDO", cls: "text-slate-400", dot: "bg-slate-500 animate-live-pulse" },
    reconnecting: { text: "RECONECTANDO", cls: "text-accent-amber", dot: "bg-accent-amber animate-live-pulse" },
    offline: { text: "SIN CONEXIÓN", cls: "text-accent-red", dot: "bg-accent-red" },
  }[connection];
  return (
    <span className={`inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.04] px-3 py-1 text-[11px] font-semibold tracking-wider ${map.cls}`}>
      <span className={`h-2 w-2 rounded-full ${map.dot}`} />
      {map.text}
    </span>
  );
}

function ModeBadge() {
  const { snapshot } = useMonitor();
  if (!snapshot) return null;
  const sim = snapshot.mode === "simulation";
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-[11px] font-semibold tracking-wider ${
        sim ? "border-violet-500/40 bg-violet-500/10 text-violet-300" : "border-emerald-500/40 bg-emerald-500/10 text-emerald-300"
      }`}
    >
      {sim ? "SIMULACIÓN" : "LIVE"}
    </span>
  );
}

export function Header() {
  const { range } = useMonitor();
  const navItems = [
    { to: "/", label: "Dashboard", end: true, icon: <IconActivity className="h-4 w-4" /> },
    { to: "/security", label: "Seguridad", end: false, icon: <IconShield className="h-4 w-4" /> },
    { to: "/settings", label: "Ajustes", end: false, icon: <IconSettings className="h-4 w-4" /> },
  ];
  return (
    <header className="sticky top-0 z-30 border-b border-white/[0.06] bg-ink-950/80 backdrop-blur-xl">
      <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-4 py-3 sm:px-6">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-accent-cyan/80 to-accent-blue/80 text-ink-950 shadow-glow">
            <IconActivity className="h-5 w-5" strokeWidth={2.4} />
          </div>
          <div>
            <div className="text-sm font-bold tracking-wide text-slate-50">MONITOR IA</div>
            <div className="hidden text-[10px] uppercase tracking-[0.2em] text-slate-500 sm:block">
              Observabilidad de inferencia local
            </div>
          </div>
        </div>

        <nav className="flex items-center gap-1.5">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                `inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-sm font-medium transition ${
                  isActive ? "bg-white/[0.08] text-slate-50" : "text-slate-400 hover:text-slate-200"
                }`
              }
            >
              {item.icon}
              <span className="hidden md:inline">{item.label}</span>
            </NavLink>
          ))}
        </nav>

        <div className="flex items-center gap-2">
          <ModeBadge />
          <ConnectionBadge />
          <button
            title="Exportar histórico a CSV"
            onClick={(() => {
              window.location.href = exportCsvUrl(range as Range);
            }) as () => void}
            className="btn-ghost !px-2.5"
          >
            <span className="hidden sm:inline">Exportar CSV</span>
            <IconDownload className="h-4 w-4 sm:ml-1" />
          </button>
        </div>
      </div>
    </header>
  );
}

export { RANGES };
