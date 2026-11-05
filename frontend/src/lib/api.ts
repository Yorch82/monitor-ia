/** Universidad de URLs del backend y helpers de fetch. */

import type { ChartPoint, PublicSettings, Range, TelemetrySnapshot } from "../types/telemetry";
import type { SecurityRange, SecuritySnapshot } from "../types/security";

/** Base de la API: vacío en dev/prod (Vite/nginx la proxan), o URL absoluta si se define. */
export const API_BASE = (import.meta.env.VITE_API_BASE ?? "").replace(/\/$/, "");

export function wsUrl(): string {
  if (import.meta.env.VITE_API_BASE) {
    const httpBase = API_BASE.startsWith("http") ? API_BASE : `${window.location.origin}${API_BASE}`;
    return `${httpBase.replace(/^http/, "ws")}/ws/telemetry`;
  }
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}/ws/telemetry`;
}

export function exportCsvUrl(range: Range): string {
  return `${API_BASE}/api/export.csv?range=${range}`;
}

async function getJson<T>(url: string): Promise<T> {
  const resp = await fetch(url, { headers: { Accept: "application/json" } });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return (await resp.json()) as T;
}

export function fetchHealth(): Promise<{ status: string; mode: string }> {
  return getJson(`${API_BASE}/api/health`);
}

export function fetchSnapshot(): Promise<{ snapshot: TelemetrySnapshot | null }> {
  return getJson(`${API_BASE}/api/telemetry`);
}

export function fetchHistory(range: Range): Promise<{ points: ChartPoint[]; bucket_seconds: number }> {
  return getJson(`${API_BASE}/api/history?range=${range}`);
}

export function fetchSettings(): Promise<PublicSettings> {
  return getJson(`${API_BASE}/api/settings`);
}

export function fetchSecurity(range: SecurityRange): Promise<SecuritySnapshot> {
  return getJson(`${API_BASE}/api/security?range=${range}`);
}

export async function updateSettings(patch: Partial<PublicSettings> & { thresholds?: PublicSettings["thresholds"] } & Record<string, unknown>): Promise<PublicSettings> {
  const resp = await fetch(`${API_BASE}/api/settings`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
  if (!resp.ok) {
    const body = (await resp.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(body?.detail ?? `HTTP ${resp.status}`);
  }
  return (await resp.json()) as PublicSettings;
}

export async function resetSession(): Promise<void> {
  const resp = await fetch(`${API_BASE}/api/session/reset`, { method: "POST" });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
}

export async function resetSettings(): Promise<PublicSettings> {
  const resp = await fetch(`${API_BASE}/api/settings/reset`, { method: "POST" });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return (await resp.json()) as PublicSettings;
}
