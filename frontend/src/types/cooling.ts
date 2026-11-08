/** Tipos de la pestaña Refrigeración (GET /api/cooling). */

export type CoolingProfile = "silent" | "balanced" | "max" | "auto" | "custom";
export type CoolingSource = "cpu" | "gpu" | "system" | "storage";

export interface CoolingControl {
  enabled: boolean;
  writable: boolean;
  released: boolean;
  profile: CoolingProfile;
  emergency_active: boolean;
  min_pwm_pct: number;
  emergency_temp_c: number;
  emergency_release_c: number;
  restore_on_exit: boolean;
  last_error: string | null;
  note: string;
}

export interface CoolingTemperature {
  id: string;
  label: string;
  source: CoolingSource;
  value_c: number;
  chip: string;
}

export interface CoolingFan {
  id: string;
  label: string;
  kind: "system" | "gpu";
  source: string;
  rpm: number | null;
  pwm_pct: number | null;
  controllable: boolean;
  min_pwm_pct: number;
  last_error: string | null;
  is_protected?: boolean;
}

export interface CoolingProfileInfo {
  id: CoolingProfile;
  label: string;
  description: string;
  target_pwm_pct: number | null;
}

export interface CoolingSnapshot {
  updated_at: number;
  mode: "simulation" | "live";
  available: boolean;
  control: CoolingControl;
  summary: {
    cpu_temp_c: number | null;
    gpu_temp_c: number | null;
    max_temp_c: number | null;
    fan_count: number;
    controllable_fans: number;
    avg_fan_rpm: number | null;
  };
  temperatures: CoolingTemperature[];
  fans: CoolingFan[];
  profiles: CoolingProfileInfo[];
}
