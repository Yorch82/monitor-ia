/** Tipos de la pestaña Seguridad (espejo del endpoint /api/security). */

export type SecurityRange = "1h" | "24h" | "7d";
export type SecurityClassification = "bot" | "human" | "unknown";

export interface SecurityLogSource {
  available?: boolean;
  paths?: string[];
  error?: string | null;
}

export interface GeoIpSource {
  enabled: boolean;
  provider: string;
  lookups_ok: number;
  lookups_failed: number;
}

export interface SecuritySources {
  enabled: boolean;
  ssh: SecurityLogSource;
  firewall: SecurityLogSource;
  web: SecurityLogSource;
  geoip: GeoIpSource;
  retention_hours: number;
}

export interface SecuritySummary {
  total_events: number;
  ssh_failed: number;
  ssh_success: number;
  ssh_scan: number;
  firewall_blocks: number;
  web_suspicious: number;
  unique_ips: number;
  countries: number;
  bots: number;
  humans: number;
  unknown: number;
  bot_pct: number | null;
  events_per_hour: number;
  last_ssh_success: {
    ts: number;
    ip: string;
    username: string | null;
    country_code: string | null;
    country: string | null;
  } | null;
  top_port: { port: number; attempts: number } | null;
  top_country: { country_code: string; country: string; events: number; ips: number } | null;
}

export interface SecurityTimelinePoint {
  t: number;
  ssh_failed: number;
  ssh_success: number;
  ssh_scan: number;
  firewall_blocks: number;
  web_suspicious: number;
}

export interface SecurityTopIp {
  ip: string;
  events: number;
  last_ts: number;
  first_ts: number;
  ssh_failed: number;
  ssh_success: number;
  ssh_scan: number;
  firewall_blocks: number;
  web_suspicious: number;
  country_code: string | null;
  country: string | null;
  city: string | null;
  isp: string | null;
  classification: SecurityClassification;
}

export interface SecurityCountry {
  country_code: string;
  country: string;
  events: number;
  ips: number;
}

export interface SecurityCount {
  attempts: number;
}

export interface SecurityUsername {
  username: string;
  attempts: number;
}

export interface SecurityPort {
  port: number;
  attempts: number;
}

export interface SecurityPath {
  path: string;
  attempts: number;
}

export interface SecurityEvent {
  ts: number;
  kind: string;
  ip: string;
  classification: SecurityClassification;
  severity: "info" | "warning" | "critical";
  username: string | null;
  path: string | null;
  port: number | null;
  detail: string;
  user_agent: string | null;
  country_code: string | null;
  country: string | null;
  city: string | null;
}

export interface SecuritySnapshot {
  generated_at: number;
  range: SecurityRange;
  enabled: boolean;
  sources: SecuritySources;
  summary: SecuritySummary;
  timeline: SecurityTimelinePoint[];
  top_ips: SecurityTopIp[];
  top_countries: SecurityCountry[];
  top_usernames: SecurityUsername[];
  top_ports: SecurityPort[];
  top_paths: SecurityPath[];
  recent_events: SecurityEvent[];
}
