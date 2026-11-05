/** Banner de alertas + toasts visuales con auto-discarte. */

import { useEffect, useRef, useState } from "react";
import { useMonitor } from "../../state/MonitorContext";
import { IconAlert, IconX } from "../Icons";
import type { AlertItem } from "../../types/telemetry";

const SEV_STYLE = {
  warning: "border-amber-500/40 bg-amber-500/10 text-amber-200",
  critical: "border-red-500/50 bg-red-500/15 text-red-200",
} as const;

const DOT_STYLE = {
  warning: "bg-accent-amber",
  critical: "bg-accent-red",
} as const;

export function AlertBanner() {
  const { snapshot } = useMonitor();
  const [expanded, setExpanded] = useState(false);
  const alerts = snapshot?.alerts ?? [];
  if (alerts.length === 0) return null;
  const criticals = alerts.filter((a) => a.severity === "critical").length;

  return (
    <div className="mx-auto mt-3 max-w-7xl px-4 sm:px-6">
      <div
        className={`flex items-center gap-3 rounded-xl border px-4 py-2.5 text-sm ${
          criticals > 0 ? SEV_STYLE.critical : SEV_STYLE.warning
        }`}
        role="alert"
      >
        <IconAlert className="h-4 w-4 shrink-0" />
        <div className="min-w-0 flex-1">
          <div className="truncate font-medium">
            {alerts[0].message}
            {alerts.length > 1 && ` · +${alerts.length - 1} más`}
          </div>
        </div>
        {alerts.length > 1 && (
          <button className="text-xs underline-offset-2 hover:underline" onClick={() => setExpanded((v) => !v)}>
            {expanded ? "Ocultar" : "Ver todas"}
          </button>
        )}
      </div>
      {expanded && (
        <ul className="mt-2 space-y-1.5">
          {alerts.map((a) => (
            <li key={a.id} className={`flex items-center gap-2 rounded-lg border px-3 py-2 text-sm ${SEV_STYLE[a.severity]}`}>
              <span className={`h-2 w-2 rounded-full ${DOT_STYLE[a.severity]}`} />
              {a.message}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

interface ToastItem {
  key: string;
  alert: AlertItem;
}

export function AlertToasts() {
  const { snapshot, connection } = useMonitor();
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const seenRef = useRef<Set<string>>(new Set());
  const lastTsRef = useRef(0);

  // Detecta alertas "nuevas" comparando ids + timestamp del backend.
  useEffect(() => {
    if (!snapshot) return;
    if (lastTsRef.current === 0) {
      // Primer frame: registra lo existente sin tostear.
      snapshot.alerts.forEach((a) => seenRef.current.add(a.id));
      lastTsRef.current = snapshot.ts;
      return;
    }
    const fresh = snapshot.alerts.filter((a) => !seenRef.current.has(a.id));
    fresh.forEach((a) => {
      seenRef.current.add(a.id);
      setToasts((prev) => [...prev, { key: `${a.id}-${a.ts}`, alert: a }]);
    });
    // limpia los que ya no están activos
    snapshot.alerts.forEach((a) => seenRef.current.add(a.id));
    const activeIds = new Set(snapshot.alerts.map((a) => a.id));
    seenRef.current.forEach((id) => {
      if (!activeIds.has(id)) seenRef.current.delete(id);
    });
    lastTsRef.current = snapshot.ts;
  }, [snapshot]);

  // Auto-discarte a los 8 s.
  useEffect(() => {
    if (toasts.length === 0) return;
    const timer = setTimeout(() => setToasts((prev) => prev.slice(1)), 8000);
    return () => clearTimeout(timer);
  }, [toasts]);

  // Reconexión: reinicia el registro para volver a avisar si siguen activas.
  useEffect(() => {
    if (connection === "offline") {
      seenRef.current.clear();
      lastTsRef.current = 0;
    }
  }, [connection]);

  return (
    <div className="fixed bottom-4 right-4 z-50 flex w-80 flex-col gap-2">
      {toasts.map((t) => (
        <div
          key={t.key}
          className={`flex items-start gap-2 rounded-xl border p-3 text-sm shadow-card backdrop-blur ${
            SEV_STYLE[t.alert.severity]
          }`}
        >
          <IconAlert className="mt-0.5 h-4 w-4 shrink-0" />
          <div className="flex-1">
            <div className="font-semibold uppercase tracking-wider text-[10px] opacity-80">
              {t.alert.severity === "critical" ? "Alerta crítica" : "Aviso"}
            </div>
            <div className="mt-0.5">{t.alert.message}</div>
          </div>
          <button onClick={() => setToasts((prev) => prev.filter((x) => x.key !== t.key))} className="opacity-60 hover:opacity-100">
            <IconX className="h-4 w-4" />
          </button>
        </div>
      ))}
    </div>
  );
}
