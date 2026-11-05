/** Tipos del telemetría — espejo exacto de los dataclasses del backend (asdict). */

export type AlertSeverity = "warning" | "critical";
export type ContextLevel = "ok" | "warning" | "critical" | "none";
export type TokenSource = "proxy" | "prometheus" | "simulation" | "none";
export type Mode = "simulation" | "live";

export interface RequestUsage {
  ts: number;
  input_tokens: number;
  output_tokens: number;
  duration_s: number;
  model: string | null;
  total_tokens: number;
  tokens_per_second: number;
}

export interface ContextState {
  available: boolean;
  used_tokens: number | null;
  max_tokens: number | null;
  percent: number | null;
  level: ContextLevel;
  source: string;
}

export interface TokensSnapshot {
  source: TokenSource;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  requests: number;
  instant_input_per_s: number;
  instant_output_per_s: number;
  moving_avg_output_per_s: number;
  last_request: RequestUsage | null;
  recent_requests: RequestUsage[];
  context: ContextState;
}

export interface GpuReading {
  index: number;
  name: string;
  vendor: string;
  utilization_pct: number | null;
  memory_used_mb: number | null;
  memory_total_mb: number | null;
  temperature_c: number | null;
  fan_pct: number | null;
  power_w: number | null;
  power_limit_w: number | null;
  memory_pct: number | null;
  power_pct: number | null;
}

export interface HardwareStatus {
  gpu_available: boolean;
  gpu_error: string | null;
  provider: string;
  mode: Mode;
}

export interface PowerSnapshot {
  current_w: number | null;
  limit_w: number | null;
  percent: number | null;
  energy_session_wh: number;
  energy_session_kwh: number;
  available: boolean;
}

export interface CostSnapshot {
  price_per_kwh: number;
  session_cost: number;
  cost_per_hour: number | null;
  projection_day: number | null;
  projection_month: number | null;
  cost_per_1k_tokens: number | null;
  daily_cost: number;
  daily_limit: number | null;
  daily_pct: number | null;
}

export interface SystemReading {
  cpu_pct: number | null;
  cpu_count: number | null;
  ram_used_gb: number | null;
  ram_total_gb: number | null;
  ram_pct: number | null;
  swap_used_gb: number | null;
  swap_total_gb: number | null;
  swap_pct: number | null;
  uptime_s: number | null;
}

export interface InferenceStatus {
  status: "online" | "offline" | "unknown";
  engine: string;
  model: string;
  latency_ms: number | null;
  error: string | null;
  context_hint_tokens: number | null;
  context_hint_source: string;
}

export interface AlertItem {
  id: string;
  severity: AlertSeverity;
  message: string;
  value: number;
  threshold: number;
  ts: number;
}

export interface TelemetrySnapshot {
  ts: number;
  ts_iso: string;
  mode: Mode;
  interval_s: number;
  tokens: TokensSnapshot;
  gpus: GpuReading[];
  hardware: HardwareStatus;
  power: PowerSnapshot;
  cost: CostSnapshot;
  system: SystemReading;
  inference: InferenceStatus;
  alerts: AlertItem[];
  gpu_avg_pct: number | null;
  gpu_temp_max_c: number | null;
  vram_avg_pct: number | null;
}

/** Punto de las gráficas (idéntico shape en histórico y en vivo). */
export interface ChartPoint {
  t: number;
  input_per_s: number | null;
  output_per_s: number | null;
  moving_avg_per_s: number | null;
  context_pct: number | null;
  gpu_pct: number | null;
  vram_pct: number | null;
  gpu_temp_c: number | null;
  power_w: number | null;
  ram_pct: number | null;
  cpu_pct: number | null;
  cost_per_hour: number | null;
  input_total: number;
  output_total: number;
}

export type Range = "1m" | "15m" | "1h" | "24h";

/** Settings runtime (API key nunca se devuelve). */
export interface AlertThresholds {
  context_pct: number;
  gpu_temp_c: number;
  vram_pct: number;
  ram_pct: number;
  daily_cost_eur: number;
}

export interface PublicSettings {
  simulation_mode: boolean;
  refresh_interval_ms: number;
  price_per_kwh: number;
  inference_base_url: string;
  inference_metrics_url: string;
  inference_api_key_set: boolean;
  inference_model: string;
  context_window: number;
  token_source: "auto" | "proxy" | "prometheus" | "none";
  gpu_provider: "auto" | "nvidia" | "amd" | "apple" | "none";
  webhook_url: string;
  history_retention_hours: number;
  thresholds: AlertThresholds;
}
