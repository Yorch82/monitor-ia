/** Formateadores de unidades (es-ES). */

const nf = (min: number, max: number) =>
  new Intl.NumberFormat("es-ES", { minimumFractionDigits: min, maximumFractionDigits: max });

export function fmtNum(value: number | null | undefined, maxDigits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const digits = Number.isInteger(value) ? 0 : maxDigits;
  return nf(digits, maxDigits).format(value);
}

export function fmtInt(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return new Intl.NumberFormat("es-ES").format(value);
}

/** Tokens grandes en notación compacta (12.4k, 3.2M). */
export function fmtCompact(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return new Intl.NumberFormat("es-ES", { notation: "compact", maximumFractionDigits: 1 }).format(value);
}

export function fmtEur(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${nf(digits === 2 ? 2 : digits, digits).format(value)} €`;
}

export function fmtGb(mb: number | null | undefined): string {
  if (mb === null || mb === undefined) return "—";
  return `${nf(1, 1).format(mb / 1024)} GB`;
}

export function fmtMs(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return `${nf(0, 0).format(value)} ms`;
}

export function fmtUptime(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return "—";
  const s = Math.floor(seconds);
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (d > 0) return `${d}d ${h}h`;
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m ${s % 60}s`;
}

export function fmtTime(ms: number, range: string): string {
  const d = new Date(ms);
  if (range === "24h") {
    return d.toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit" });
  }
  return d.toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export function fmtRelative(ts: number): string {
  const delta = Math.max(0, Date.now() / 1000 - ts);
  if (delta < 10) return "ahora";
  if (delta < 60) return `hace ${Math.floor(delta)} s`;
  if (delta < 3600) return `hace ${Math.floor(delta / 60)} min`;
  if (delta < 86400) return `hace ${Math.floor(delta / 3600)} h`;
  return `hace ${Math.floor(delta / 86400)} d`;
}

export function fmtDuration(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds <= 0) return "—";
  return seconds < 100 ? `${nf(1, 2).format(seconds)} s` : `${nf(0, 0).format(seconds)} s`;
}
