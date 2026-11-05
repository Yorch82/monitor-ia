/** Página de ajustes: precio, muestreo, inferencia, umbrales, webhook; acciones de reinicio. */

import { useEffect, useState, type ReactNode } from "react";
import {
  fetchSettings,
  resetSession,
  resetSettings,
  updateSettings,
} from "../lib/api";
import type { AlertThresholds, PublicSettings } from "../types/telemetry";
import { Card } from "../components/ui/Card";
import { IconCheck, IconEuro, IconRefresh, IconServer, IconSettings, IconWifi } from "../components/Icons";

type Status = { kind: "ok" | "err"; msg: string } | null;

export function Settings() {
  const [form, setForm] = useState<PublicSettings | null>(null);
  const [apiKey, setApiKey] = useState("");
  const [clearKey, setClearKey] = useState(false);
  const [status, setStatus] = useState<Status>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    fetchSettings()
      .then(setForm)
      .catch((e) => setStatus({ kind: "err", msg: `No se pudo cargar la configuración: ${e}` }));
  }, []);

  if (!form) {
    return (
      <div className="mx-auto flex h-[50vh] max-w-4xl items-center justify-center text-slate-500">
        Cargando ajustes…
      </div>
    );
  }

  const set = <K extends keyof PublicSettings>(key: K, value: PublicSettings[K]) =>
    setForm((f) => (f ? { ...f, [key]: value } : f));

  const setThreshold = (key: keyof AlertThresholds, value: number) =>
    setForm((f) => (f ? { ...f, thresholds: { ...f.thresholds, [key]: value } } : f));

  const save = async () => {
    if (!form) return;
    setBusy(true);
    setStatus(null);
    try {
      // La API key solo se envía si el usuario la escribió (o marcó "borrar").
      const payload: Record<string, unknown> = { ...form };
      if (apiKey.trim()) payload.inference_api_key = apiKey.trim();
      if (clearKey) payload.inference_api_key = "";
      delete payload.inference_api_key_set;
      const saved = await updateSettings(payload);
      setForm(saved);
      setApiKey("");
      setClearKey(false);
      setStatus({ kind: "ok", msg: "Ajustes guardados y aplicados en caliente." });
    } catch (e) {
      setStatus({ kind: "err", msg: e instanceof Error ? e.message : String(e) });
    } finally {
      setBusy(false);
    }
  };

  const restoreDefaults = async () => {
    setBusy(true);
    try {
      setForm(await resetSettings());
      setStatus({ kind: "ok", msg: "Ajustes restaurados a los valores del .env." });
    } catch (e) {
      setStatus({ kind: "err", msg: e instanceof Error ? e.message : String(e) });
    } finally {
      setBusy(false);
    }
  };

  const doResetSession = async () => {
    try {
      await resetSession();
      setStatus({ kind: "ok", msg: "Sesión reiniciada (tokens, energía y coste)." });
    } catch (e) {
      setStatus({ kind: "err", msg: e instanceof Error ? e.message : String(e) });
    }
  };

  return (
    <div className="mx-auto max-w-4xl space-y-4 px-4 pb-16 pt-6 sm:px-6">
      <div className="flex items-center gap-3">
        <span className="text-accent-cyan"><IconSettings className="h-5 w-5" /></span>
        <h1 className="text-lg font-bold text-slate-50">Ajustes</h1>
      </div>

      {status && (
        <div
          className={`rounded-xl border px-4 py-2.5 text-sm ${
            status.kind === "ok"
              ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-200"
              : "border-red-500/30 bg-red-500/10 text-red-200"
          }`}
        >
          {status.msg}
        </div>
      )}

      {/* ── Energía y coste ──────────────────────────────────────────────── */}
      <Card title="Energía y coste" icon={<IconEuro className="h-4 w-4" />}>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label="Precio del kWh (€/kWh)" help="Coste eléctrico de tu tarifa, impuestos incluidos.">
            <input
              type="number" step="0.001" min="0" className="input"
              value={form.price_per_kwh}
              onChange={(e) => set("price_per_kwh", Number(e.target.value))}
            />
          </Field>
          <Field label="Límite de coste diario (€)" help="Alerta (y webhook) cuando el coste del día lo supere.">
            <input
              type="number" step="0.1" min="0" className="input"
              value={form.thresholds.daily_cost_eur}
              onChange={(e) => setThreshold("daily_cost_eur", Number(e.target.value))}
            />
          </Field>
        </div>
      </Card>

      {/* ── Servidor de inferencia ───────────────────────────────────────── */}
      <Card title="Servidor de inferencia" icon={<IconServer className="h-4 w-4" />}>
        <div className="space-y-4">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Field label="URL base (OpenAI-compatible)" help="Ollama http://host:11434/v1 · llama.cpp http://host:8080/v1 · vLLM http://host:8000/v1">
              <input className="input" value={form.inference_base_url}
                     onChange={(e) => set("inference_base_url", e.target.value)} />
            </Field>
            <Field label="URL de métricas Prometheus (opcional)" help="Vacío → se deduce {base−/v1}/metrics. Solo vLLM/llama.cpp.">
              <input className="input" value={form.inference_metrics_url}
                     onChange={(e) => set("inference_metrics_url", e.target.value)} />
            </Field>
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <Field label="Modelo (display)" help="Se muestra si el server no reporta modelo.">
              <input className="input" value={form.inference_model}
                     onChange={(e) => set("inference_model", e.target.value)} />
            </Field>
            <Field label="Ventana de contexto (tokens)" help="Se usa si no se detecta en el servidor.">
              <input type="number" min="256" step="256" className="input" value={form.context_window}
                     onChange={(e) => set("context_window", Number(e.target.value))} />
            </Field>
            <Field label="Fuente de tokens" help="auto: Prometheus si existe, si no el proxy.">
              <select className="input" value={form.token_source}
                      onChange={(e) => set("token_source", e.target.value as PublicSettings["token_source"])}>
                <option value="auto">auto</option>
                <option value="proxy">proxy (recomendado)</option>
                <option value="prometheus">prometheus</option>
                <option value="none">none</option>
              </select>
            </Field>
          </div>
          <Field
            label={form.inference_api_key_set ? "API key (ya guardada — escribe una nueva para cambiarla)" : "API key (opcional)"}
            help="Se guarda en la SQLite local del servidor; nunca se devuelve al navegador."
          >
            <div className="flex items-center gap-3">
              <input className="input" type="password" placeholder={form.inference_api_key_set ? "••••••••" : ""}
                     value={apiKey} onChange={(e) => setApiKey(e.target.value)} />
              {form.inference_api_key_set && (
                <label className="flex shrink-0 cursor-pointer items-center gap-1.5 text-xs text-slate-400">
                  <input type="checkbox" checked={clearKey} onChange={(e) => setClearKey(e.target.checked)} className="h-4 w-4 accent-cyan-400" />
                  borrar
                </label>
              )}
            </div>
          </Field>
          <div className="rounded-xl border border-accent-cyan/20 bg-accent-cyan/[0.06] px-3 py-2 text-[11px] leading-relaxed text-slate-300">
            <b className="text-accent-cyan">Integración por proxy:</b> apunta tu cliente de IA a{" "}
            <code className="rounded bg-black/40 px-1.5 py-0.5 font-mono">{`${window.location.origin}/proxy/v1`}</code>{" "}
            (endpoint de chat/completions) y este backend reenviará al servidor real registrando
            los tokens, la velocidad y el contexto de cada petición.
          </div>
        </div>
      </Card>

      {/* ── Muestreo y modo ──────────────────────────────────────────────── */}
      <Card title="Muestreo y modo" icon={<IconRefresh className="h-4 w-4" />}>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <Field label="Intervalo de refresco (ms)" help="Cada cuánto se muestrean y emiten métricas (250–60000 ms).">
            <input type="number" min="250" step="250" max="60000" className="input"
                   value={form.refresh_interval_ms}
                   onChange={(e) => set("refresh_interval_ms", Number(e.target.value))} />
          </Field>
          <Field label="Modo simulación" help="Datos sintéticos sin hardware; úsalo para probar la app.">
            <label className="mt-2.5 inline-flex cursor-pointer items-center gap-2 text-sm">
              <input type="checkbox" checked={form.simulation_mode} className="h-4 w-4 accent-cyan-400"
                     onChange={(e) => set("simulation_mode", e.target.checked)} />
              {form.simulation_mode ? "activado" : "desactivado"}
            </label>
          </Field>
          <Field label="Proveedor de GPU" help="auto detecta NVIDIA → AMD → Apple Silicon.">
            <select className="input" value={form.gpu_provider}
                    onChange={(e) => set("gpu_provider", e.target.value as PublicSettings["gpu_provider"])}>
              <option value="auto">auto</option>
              <option value="nvidia">nvidia</option>
              <option value="amd">amd</option>
              <option value="apple">apple</option>
              <option value="none">none</option>
            </select>
          </Field>
        </div>
        <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label="Webhook de alertas (opcional)" help="POST JSON ({app, type, alert}) cada vez que una alerta se activa o escala.">
            <input className="input" placeholder="https://hooks…/token" value={form.webhook_url}
                   onChange={(e) => set("webhook_url", e.target.value)} />
          </Field>
          <Field label="Retención del histórico (horas)" help="1–336 h; se poda automáticamente.">
            <input type="number" min="1" max="336" className="input" value={form.history_retention_hours}
                   onChange={(e) => set("history_retention_hours", Number(e.target.value))} />
          </Field>
        </div>
      </Card>

      {/* ── Umbrales de alerta ───────────────────────────────────────────── */}
      <Card title="Umbrales de alerta" icon={<IconWifi className="h-4 w-4" />}>
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <NumField label="Contexto %" value={form.thresholds.context_pct}
                    onChange={(v) => setThreshold("context_pct", v)} />
          <NumField label="GPU temp ºC" value={form.thresholds.gpu_temp_c}
                    onChange={(v) => setThreshold("gpu_temp_c", v)} />
          <NumField label="VRAM %" value={form.thresholds.vram_pct}
                    onChange={(v) => setThreshold("vram_pct", v)} />
          <NumField label="RAM %" value={form.thresholds.ram_pct}
                    onChange={(v) => setThreshold("ram_pct", v)} />
        </div>
      </Card>

      {/* ── acciones ─────────────────────────────────────────────────────── */}
      <div className="flex flex-wrap items-center justify-between gap-3 pb-4">
        <button className="btn-danger" onClick={doResetSession} disabled={busy}>
          <IconRefresh className="h-4 w-4" /> Reiniciar sesión
        </button>
        <div className="flex items-center gap-2">
          <button className="btn-ghost" onClick={restoreDefaults} disabled={busy}>
            Restaurar defaults (.env)
          </button>
          <button className="btn-primary" onClick={save} disabled={busy}>
            <IconCheck className="h-4 w-4" /> {busy ? "Guardando…" : "Guardar ajustes"}
          </button>
        </div>
      </div>
    </div>
  );
}

function Field({ label, help, children }: { label: string; help?: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium text-slate-300">{label}</span>
      {children}
      {help && <span className="mt-1 block text-[10px] leading-relaxed text-slate-500">{help}</span>}
    </label>
  );
}

function NumField({ label, value, onChange }: { label: string; value: number; onChange: (v: number) => void }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium text-slate-300">{label}</span>
      <input type="number" className="input" value={value} onChange={(e) => onChange(Number(e.target.value))} />
    </label>
  );
}
