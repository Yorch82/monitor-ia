/** Mapeo snapshot → punto de gráfica y constantes de rangos. */

import type { ChartPoint, Range, TelemetrySnapshot } from "../types/telemetry";

export const RANGE_MS: Record<Range, number> = {
  "1m": 60_000,
  "15m": 900_000,
  "1h": 3_600_000,
  "24h": 86_400_000,
};

export const RANGES: Range[] = ["1m", "15m", "1h", "24h"];

export function rangeLabel(r: Range): string {
  return { "1m": "1 min", "15m": "15 min", "1h": "1 hora", "24h": "24 horas" }[r];
}

/** Convierte el snapshot del WS en un punto (1 s) para la gráfica en vivo. */
export function snapshotToPoint(s: TelemetrySnapshot): ChartPoint {
  return {
    t: Math.round(s.ts * 1000),
    input_per_s: s.tokens?.instant_input_per_s ?? null,
    output_per_s: s.tokens?.instant_output_per_s ?? null,
    moving_avg_per_s: s.tokens?.moving_avg_output_per_s ?? null,
    context_pct: s.tokens?.context?.percent ?? null,
    gpu_pct: s.gpu_avg_pct ?? null,
    gpu_temp_c: s.gpu_temp_max_c ?? null,
    vram_pct: s.vram_avg_pct ?? null,
    power_w: s.power?.current_w ?? null,
    ram_pct: s.system?.ram_pct ?? null,
    cpu_pct: s.system?.cpu_pct ?? null,
    cost_per_hour: s.cost?.cost_per_hour ?? null,
    input_total: s.tokens?.input_tokens ?? 0,
    output_total: s.tokens?.output_tokens ?? 0,
  };
}

/** Normaliza los puntos del histórico (pueden venir con nulls sueltos). */
export function normalizeHistory(points: ChartPoint[]): ChartPoint[] {
  return points.map((p) => ({
    ...p,
    input_per_s: p.input_per_s ?? 0,
    output_per_s: p.output_per_s ?? 0,
    moving_avg_per_s: p.moving_avg_per_s ?? null,
  }));
}
