/** Pestaña Seguridad: SSH, firewall, escaneos web, bot/humano y geolocalización. */

import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { fetchSecurity } from "../lib/api";
import { fmtInt, fmtNum, fmtRelative } from "../lib/format";
import { Card } from "../components/ui/Card";
import { KpiCard } from "../components/dashboard/KpiCards";
import {
  IconAlert,
  IconCheck,
  IconGlobe,
  IconMapPin,
  IconRefresh,
  IconShield,
  IconTerminal,
  IconUserShield,
} from "../components/Icons";
import type {
  SecurityClassification,
  SecurityEvent,
  SecurityRange,
  SecuritySnapshot,
} from "../types/security";

const SECURITY_RANGES: SecurityRange[] = ["1h", "24h", "7d"];
const RANGE_LABEL: Record<SecurityRange, string> = { "1h": "1 h", "24h": "24 h", "7d": "7 días" };

const KIND_META: Record<string, { label: string; color: string }> = {
  ssh_failed: { label: "SSH fallido", color: "#f87171" },
  ssh_success: { label: "Login SSH", color: "#34d399" },
  ssh_scan: { label: "Escaneo SSH", color: "#fbbf24" },
  firewall_block: { label: "Firewall", color: "#fb923c" },
  http_suspicious: { label: "Web sospechosa", color: "#a78bfa" },
};

const CLASS_META: Record<SecurityClassification, { label: string; cls: string }> = {
  bot: { label: "Bot", cls: "bg-red-500/15 text-red-300 border-red-500/30" },
  human: { label: "Humano", cls: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30" },
  unknown: { label: "Desconocido", cls: "bg-slate-500/15 text-slate-300 border-slate-500/30" },
};

function flag(code: string | null | undefined): string {
  if (!code) return "🌐";
  if (code === "--") return "🏠";
  if (code === "??" || code.length !== 2) return "🌐";
  return String.fromCodePoint(...code.toUpperCase().split("").map((c) => 127397 + c.charCodeAt(0)));
}

function fmtEventTime(ts: number, range: SecurityRange): string {
  const d = new Date(ts * 1000);
  if (range === "7d") {
    return d.toLocaleString("es-ES", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
  }
  return d.toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit" });
}

export function Security() {
  const [range, setRange] = useState<SecurityRange>("24h");
  const [data, setData] = useState<SecuritySnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const snapshot = await fetchSecurity(range);
      setData(snapshot);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo cargar la seguridad");
    } finally {
      setLoading(false);
    }
  }, [range]);

  useEffect(() => {
    setLoading(true);
    void load();
    const timer = setInterval(() => void load(), 10_000);
    return () => clearInterval(timer);
  }, [load]);

  const summary = data?.summary;
  const sources = data?.sources;
  const timeline = data?.timeline ?? [];

  const botData = useMemo(() => {
    if (!summary) return [];
    return [
      { name: "Bots", value: summary.bots, color: "#f87171" },
      { name: "Humanos", value: summary.humans, color: "#34d399" },
      { name: "Desconocidos", value: summary.unknown, color: "#64748b" },
    ].filter((d) => d.value > 0);
  }, [summary]);

  return (
    <div className="mx-auto max-w-7xl space-y-3 px-4 pb-10 pt-4 sm:px-6">
      {/* ── cabecera ─────────────────────────────────────────────────────── */}
      <div className="flex flex-wrap items-center justify-between gap-3 px-1">
        <div className="flex items-center gap-2.5">
          <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-accent-red/10 text-accent-red">
            <IconShield className="h-5 w-5" />
          </span>
          <div>
            <h1 className="text-base font-bold text-slate-50">Seguridad del servidor</h1>
            <p className="text-[11px] text-slate-500">
              Intentos de conexión, SSH, firewall y escaneos web · actualización cada 10 s
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1 rounded-lg border border-white/10 bg-white/[0.03] p-0.5">
            {SECURITY_RANGES.map((r) => (
              <button
                key={r}
                onClick={() => setRange(r)}
                className={`rounded-md px-2.5 py-1 text-[11px] font-semibold transition ${
                  r === range ? "bg-accent-cyan/90 text-ink-950" : "text-slate-400 hover:text-slate-200"
                }`}
              >
                {RANGE_LABEL[r].toUpperCase()}
              </button>
            ))}
          </div>
          <button onClick={() => void load()} className="btn-ghost !px-2.5" title="Actualizar ahora">
            <IconRefresh className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-2 text-sm text-amber-200">
          {error} — reintentando…
        </div>
      )}

      {data && !data.enabled ? (
        <Card title="Monitor de seguridad desactivado">
          <p className="text-sm text-slate-400">
            Actívalo en <code className="rounded bg-black/30 px-1">.env</code> con{" "}
            <code className="rounded bg-black/30 px-1">SECURITY_ENABLED=true</code> y recrea el backend.
          </p>
        </Card>
      ) : (
        <>
          {/* fuentes */}
          <div className="flex flex-wrap items-center gap-2 px-1">
            <SourceChip label="SSH" ok={!!sources?.ssh.available} hint={sources?.ssh.error ?? "auth.log / secure"} />
            <SourceChip label="Firewall UFW" ok={!!sources?.firewall.available} hint={sources?.firewall.error ?? "ufw.log"} />
            <SourceChip label="Web nginx" ok={!!sources?.web.available} hint={sources?.web.error ?? "security.log"} />
            <SourceChip
              label={`GeoIP ${sources?.geoip.enabled ? "activo" : "off"}`}
              ok={!!sources?.geoip.enabled}
              hint={sources ? `${sources.geoip.provider} · ${sources.geoip.lookups_ok} consultas` : undefined}
              neutral={!sources?.geoip.enabled}
            />
            <span className="ml-auto text-[10px] uppercase tracking-widest text-slate-600">
              retención {sources?.retention_hours ?? 168} h
            </span>
          </div>

          {/* KPIs */}
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
            <KpiCard
              label="SSH fallidos"
              value={fmtInt(summary?.ssh_failed ?? 0)}
              hint={`${fmtInt(summary?.ssh_scan ?? 0)} escaneos SSH`}
              icon={<IconTerminal className="h-5 w-5" />}
              accent={summary && summary.ssh_failed > 0 ? "red" : "emerald"}
              footer={summary?.last_ssh_success ? <span>último login: {fmtRelative(summary.last_ssh_success.ts)}</span> : <span>sin logins correctos</span>}
            />
            <KpiCard
              label="IPs únicas"
              value={fmtInt(summary?.unique_ips ?? 0)}
              hint={`${fmtNum(summary?.events_per_hour ?? 0, 2)} eventos/hora`}
              icon={<IconGlobe className="h-5 w-5" />}
              accent="cyan"
              footer={<span>{fmtInt(summary?.total_events ?? 0)} eventos en el rango</span>}
            />
            <KpiCard
              label="Países"
              value={fmtInt(summary?.countries ?? 0)}
              hint={summary?.top_country ? `${flag(summary.top_country.country_code)} ${summary.top_country.country}` : "sin datos"}
              icon={<IconMapPin className="h-5 w-5" />}
              accent="blue"
              footer={<span>origen de las IPs externas</span>}
            />
            <KpiCard
              label="Logins SSH"
              value={fmtInt(summary?.ssh_success ?? 0)}
              hint={summary?.last_ssh_success ? `${summary.last_ssh_success.username ?? "?"} · ${flag(summary.last_ssh_success.country_code)} ${summary.last_ssh_success.country ?? ""}` : "sin accesos"}
              icon={<IconCheck className="h-5 w-5" />}
              accent={summary && summary.ssh_success > 0 ? "amber" : "emerald"}
              footer={<span>accesos completados correctamente</span>}
            />
            <KpiCard
              label="Web sospechosa"
              value={fmtInt(summary?.web_suspicious ?? 0)}
              hint={data?.top_paths?.[0] ? data.top_paths[0].path.slice(0, 28) : "sin escaneos web"}
              icon={<IconAlert className="h-5 w-5" />}
              accent={summary && summary.web_suspicious > 0 ? "violet" : "emerald"}
              footer={<span>{fmtInt(summary?.firewall_blocks ?? 0)} bloqueos de firewall</span>}
            />
            <KpiCard
              label="Bots"
              value={summary?.bot_pct != null ? `${fmtNum(summary.bot_pct, 0)}%` : "—"}
              hint={summary ? `${summary.bots} bots · ${summary.humans} humanos` : undefined}
              icon={<IconUserShield className="h-5 w-5" />}
              accent={summary && (summary.bot_pct ?? 0) > 70 ? "red" : "amber"}
              progress={summary?.bot_pct ?? null}
              footer={<span>clasificación por IP única</span>}
            />
          </div>

          {/* timeline + donut */}
          <div className="grid grid-cols-1 gap-3 xl:grid-cols-3">
            <Card title="Actividad de seguridad" icon={<IconShield className="h-4 w-4" />} className="xl:col-span-2">
              {timeline.length === 0 ? (
                <EmptyBlock text="Sin eventos en este rango todavía." />
              ) : (
                <div className="h-[260px]">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={timeline} margin={{ top: 6, right: 8, left: 0, bottom: 0 }}>
                      <CartesianGrid stroke="rgba(255,255,255,0.05)" vertical={false} />
                      <XAxis
                        dataKey="t"
                        tickFormatter={(v) => fmtEventTime((v as number) / 1000, range)}
                        tick={{ fill: "#64748b", fontSize: 10 }}
                        axisLine={false}
                        tickLine={false}
                        minTickGap={50}
                      />
                      <YAxis tick={{ fill: "#64748b", fontSize: 10 }} axisLine={false} tickLine={false} width={34} allowDecimals={false} />
                      <Tooltip content={<SecurityTooltip range={range} />} />
                      <Bar dataKey="ssh_failed" name="SSH fallidos" stackId="a" fill="#f87171" radius={[0, 0, 0, 0]} />
                      <Bar dataKey="ssh_scan" name="Escaneos SSH" stackId="a" fill="#fbbf24" />
                      <Bar dataKey="firewall_blocks" name="Firewall" stackId="a" fill="#fb923c" />
                      <Bar dataKey="web_suspicious" name="Web sospechosa" stackId="a" fill="#a78bfa" />
                      <Bar dataKey="ssh_success" name="Logins SSH" stackId="a" fill="#34d399" radius={[3, 3, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}
              <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[11px]">
                {[
                  ["ssh_failed", "SSH fallidos", "#f87171"],
                  ["ssh_scan", "Escaneos SSH", "#fbbf24"],
                  ["firewall_blocks", "Firewall", "#fb923c"],
                  ["web_suspicious", "Web sospechosa", "#a78bfa"],
                  ["ssh_success", "Logins SSH", "#34d399"],
                ].map(([key, label, color]) => (
                  <span key={key} className="flex items-center gap-1.5 text-slate-400">
                    <span className="h-1.5 w-3 rounded-full" style={{ background: color }} />
                    {label}
                  </span>
                ))}
              </div>
            </Card>

            <Card title="Bots vs humanos" icon={<IconUserShield className="h-4 w-4" />}>
              {botData.length === 0 ? (
                <EmptyBlock text="Aún no hay IPs clasificadas." />
              ) : (
                <div>
                  <div className="relative h-[190px]">
                    <ResponsiveContainer width="100%" height="100%">
                      <PieChart>
                        <Pie data={botData} dataKey="value" nameKey="name" innerRadius={58} outerRadius={80} paddingAngle={3} stroke="none">
                          {botData.map((d) => (
                            <Cell key={d.name} fill={d.color} />
                          ))}
                        </Pie>
                        <Tooltip
                          contentStyle={{ background: "#0a0e18", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 8, fontSize: 12 }}
                          itemStyle={{ color: "#e2e8f0" }}
                        />
                      </PieChart>
                    </ResponsiveContainer>
                    <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
                      <span className="font-mono text-2xl font-semibold text-slate-50">{fmtInt(summary?.unique_ips ?? 0)}</span>
                      <span className="text-[10px] uppercase tracking-widest text-slate-500">IPs únicas</span>
                    </div>
                  </div>
                  <div className="mt-1 space-y-1.5">
                    {botData.map((d) => (
                      <div key={d.name} className="flex items-center justify-between text-xs">
                        <span className="flex items-center gap-2 text-slate-400">
                          <span className="h-2 w-2 rounded-full" style={{ background: d.color }} />
                          {d.name}
                        </span>
                        <span className="font-mono text-slate-200">{fmtInt(d.value)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </Card>
          </div>

          {/* top IPs + países */}
          <div className="grid grid-cols-1 gap-3 xl:grid-cols-3">
            <Card title="IPs con más actividad" icon={<IconGlobe className="h-4 w-4" />} className="xl:col-span-2">
              {(data?.top_ips.length ?? 0) === 0 ? (
                <EmptyBlock text="Sin IPs en el rango seleccionado." />
              ) : (
                <div className="-mx-1 overflow-x-auto">
                  <table className="w-full min-w-[640px] text-left text-xs">
                    <thead className="text-[10px] uppercase tracking-widest text-slate-500">
                      <tr className="border-b border-white/[0.06]">
                        <th className="px-1 py-2 font-medium">IP / país</th>
                        <th className="px-1 py-2 font-medium">Tipo</th>
                        <th className="px-1 py-2 text-right font-medium">SSH</th>
                        <th className="px-1 py-2 text-right font-medium">UFW</th>
                        <th className="px-1 py-2 text-right font-medium">Web</th>
                        <th className="px-1 py-2 text-right font-medium">Total</th>
                        <th className="px-1 py-2 text-right font-medium">Última</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(data?.top_ips ?? []).map((ip) => (
                        <tr key={ip.ip} className="border-b border-white/[0.035] last:border-0 hover:bg-white/[0.02]">
                          <td className="px-1 py-2">
                            <div className="flex items-center gap-2">
                              <span className="text-base leading-none">{flag(ip.country_code)}</span>
                              <div className="min-w-0">
                                <div className="font-mono text-slate-200">{ip.ip}</div>
                                <div className="truncate text-[10px] text-slate-500">
                                  {[ip.country && ip.country !== "Desconocido" ? ip.country : null, ip.city, ip.isp]
                                    .filter(Boolean).join(" · ") || "sin geolocalizar"}
                                </div>
                              </div>
                            </div>
                          </td>
                          <td className="px-1 py-2">
                            <span className={`inline-flex rounded border px-1.5 py-0.5 text-[10px] font-semibold ${CLASS_META[ip.classification].cls}`}>
                              {CLASS_META[ip.classification].label}
                            </span>
                          </td>
                          <td className="px-1 py-2 text-right font-mono text-red-300/90">{ip.ssh_failed || "—"}</td>
                          <td className="px-1 py-2 text-right font-mono text-orange-300/90">{ip.firewall_blocks || "—"}</td>
                          <td className="px-1 py-2 text-right font-mono text-violet-300/90">{ip.web_suspicious || "—"}</td>
                          <td className="px-1 py-2 text-right font-mono text-slate-200">{ip.events}</td>
                          <td className="px-1 py-2 text-right text-slate-500">{fmtRelative(ip.last_ts)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Card>

            <Card title="Países de origen" icon={<IconMapPin className="h-4 w-4" />}>
              {(data?.top_countries.length ?? 0) === 0 ? (
                <EmptyBlock text="Sin geolocalizaciones todavía." />
              ) : (
                <div className="space-y-2.5">
                  {data?.top_countries.map((c) => {
                    const max = Math.max(...(data?.top_countries.map((x) => x.events) ?? [1]));
                    return (
                      <div key={`${c.country_code}-${c.country}`}>
                        <div className="mb-1 flex items-center justify-between text-xs">
                          <span className="flex items-center gap-2 text-slate-300">
                            <span>{flag(c.country_code)}</span> {c.country}
                          </span>
                          <span className="font-mono text-[11px] text-slate-400">
                            {c.events} ev · {c.ips} IPs
                          </span>
                        </div>
                        <div className="h-1.5 overflow-hidden rounded-full bg-white/[0.06]">
                          <div className="h-full rounded-full bg-accent-cyan/70" style={{ width: `${(c.events / max) * 100}%` }} />
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </Card>
          </div>

          {/* tops pequeños */}
          <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
            <TopList
              title="Usuarios objetivo"
              icon={<IconTerminal className="h-4 w-4" />}
              items={(data?.top_usernames ?? []).map((u) => ({ label: u.username, value: u.attempts }))}
              empty="Sin intentos con usuario."
            />
            <TopList
              title="Puertos escaneados"
              icon={<IconShield className="h-4 w-4" />}
              items={(data?.top_ports ?? []).map((p) => ({ label: `puerto ${p.port}`, value: p.attempts }))}
              empty="Sin bloqueos de firewall."
            />
            <TopList
              title="Rutas escaneadas"
              icon={<IconAlert className="h-4 w-4" />}
              items={(data?.top_paths ?? []).map((p) => ({ label: p.path, value: p.attempts, mono: true }))}
              empty="Sin escaneos web."
            />
          </div>

          {/* eventos recientes */}
          <Card title="Últimos eventos" icon={<IconShield className="h-4 w-4" />}>
            {(data?.recent_events.length ?? 0) === 0 ? (
              <EmptyBlock text="Todavía no se ha registrado ningún evento de seguridad." />
            ) : (
              <div className="-mx-1 max-h-[380px] overflow-auto">
                <table className="w-full min-w-[700px] text-left text-xs">
                  <thead className="sticky top-0 bg-ink-900 text-[10px] uppercase tracking-widest text-slate-500">
                    <tr className="border-b border-white/[0.06]">
                      <th className="px-1 py-2 font-medium">Hora</th>
                      <th className="px-1 py-2 font-medium">Evento</th>
                      <th className="px-1 py-2 font-medium">Origen</th>
                      <th className="px-1 py-2 font-medium">Detalle</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(data?.recent_events ?? []).map((ev, idx) => (
                      <EventRow key={`${ev.ts}-${idx}`} ev={ev} range={range} />
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>

          {/* ayuda de configuración */}
          {sources && (!sources.ssh.available || !sources.firewall.available || !sources.web.available) && (
            <Card title="Fuentes sin datos" icon={<IconAlert className="h-4 w-4" />}>
              <ul className="space-y-2 text-xs text-slate-400">
                {!sources.ssh.available && (
                  <li>
                    <b className="text-slate-300">SSH:</b> monta <code className="rounded bg-black/30 px-1">/var/log:/host/log:ro</code> en el backend
                    (ya está en <code className="rounded bg-black/30 px-1">docker-compose.yml</code>) y comprueba que exista{" "}
                    <code className="rounded bg-black/30 px-1">/var/log/auth.log</code>. Sistemas solo con journald: instala rsyslog o añade el fichero a{" "}
                    <code className="rounded bg-black/30 px-1">SECURITY_LOG_PATHS</code>.
                  </li>
                )}
                {!sources.firewall.available && (
                  <li>
                    <b className="text-slate-300">Firewall:</b> activa el logging con{" "}
                    <code className="rounded bg-black/30 px-1">sudo ufw logging on</code> (genera{" "}
                    <code className="rounded bg-black/30 px-1">/var/log/ufw.log</code>).
                  </li>
                )}
                {!sources.web.available && (
                  <li>
                    <b className="text-slate-300">Web:</b> el volumen <code className="rounded bg-black/30 px-1">nginx-logs</code> debe estar
                    montado en frontend y backend; reconstruye con <code className="rounded bg-black/30 px-1">docker compose up -d --build</code>.
                  </li>
                )}
              </ul>
            </Card>
          )}

          <p className="px-1 text-[10px] leading-relaxed text-slate-600">
            Clasificación bot/usuario por heurísticas (fallos SSH y patrones de escáner = bot). Geolocalización
            opcional vía ip-api.com con caché local de 30 días; las IPs privadas se marcan como «Red local».
          </p>
        </>
      )}
    </div>
  );
}

// ── subcomponentes ───────────────────────────────────────────────────────────

function SourceChip({
  label,
  ok,
  hint,
  neutral,
}: {
  label: string;
  ok: boolean;
  hint?: string | null;
  neutral?: boolean;
}) {
  return (
    <span
      title={hint ?? undefined}
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wider ${
        neutral
          ? "border-white/10 bg-white/[0.03] text-slate-500"
          : ok
            ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-300"
            : "border-amber-500/30 bg-amber-500/10 text-amber-300"
      }`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${neutral ? "bg-slate-600" : ok ? "bg-accent-emerald" : "bg-accent-amber"}`} />
      {label}
    </span>
  );
}

function EmptyBlock({ text }: { text: string }) {
  return (
    <div className="flex h-[180px] flex-col items-center justify-center gap-1 text-center text-sm text-slate-500">
      <span className="font-mono text-2xl text-slate-700">—</span>
      {text}
    </div>
  );
}

function TopList({
  title,
  icon,
  items,
  empty,
}: {
  title: string;
  icon: ReactNode;
  items: { label: string; value: number; mono?: boolean }[];
  empty: string;
}) {
  const max = Math.max(...items.map((i) => i.value), 1);
  return (
    <Card title={title} icon={icon}>
      {items.length === 0 ? (
        <div className="py-6 text-center text-xs text-slate-500">{empty}</div>
      ) : (
        <div className="space-y-2">
          {items.map((item, idx) => (
            <div key={`${item.label}-${idx}`}>
              <div className="mb-1 flex items-center justify-between gap-2 text-xs">
                <span className={`truncate text-slate-300 ${item.mono ? "font-mono text-[11px]" : ""}`}>{item.label}</span>
                <span className="font-mono text-[11px] text-slate-500">{item.value}</span>
              </div>
              <div className="h-1 overflow-hidden rounded-full bg-white/[0.06]">
                <div className="h-full rounded-full bg-accent-red/60" style={{ width: `${(item.value / max) * 100}%` }} />
              </div>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

function EventRow({ ev, range }: { ev: SecurityEvent; range: SecurityRange }) {
  const meta = KIND_META[ev.kind] ?? { label: ev.kind, color: "#94a3b8" };
  return (
    <tr className="border-b border-white/[0.035] last:border-0 hover:bg-white/[0.02]">
      <td className="whitespace-nowrap px-1 py-2 text-slate-500">{fmtEventTime(ev.ts, range)}</td>
      <td className="px-1 py-2">
        <span className="inline-flex items-center gap-1.5 whitespace-nowrap">
          <span className="h-1.5 w-1.5 rounded-full" style={{ background: meta.color }} />
          <span className="text-slate-300">{meta.label}</span>
        </span>
      </td>
      <td className="px-1 py-2">
        <div className="flex items-center gap-1.5 whitespace-nowrap">
          <span>{flag(ev.country_code)}</span>
          <span className="font-mono text-slate-300">{ev.ip}</span>
          {ev.country && ev.country !== "Desconocido" && ev.country !== "Red local" && (
            <span className="text-[10px] text-slate-600">{ev.country}</span>
          )}
        </div>
      </td>
      <td className="max-w-[420px] truncate px-1 py-2 text-slate-500" title={ev.detail}>
        {ev.detail || ev.path || ev.username || "—"}
      </td>
    </tr>
  );
}

function SecurityTooltip({
  active,
  payload,
  label,
  range,
}: {
  active?: boolean;
  payload?: Array<{ name?: string; value?: number; color?: string; dataKey?: string }>;
  label?: number;
  range: SecurityRange;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-white/10 bg-ink-900/95 px-3 py-2 text-xs shadow-card backdrop-blur">
      <div className="mb-1 font-semibold text-slate-300">{fmtEventTime((label as number) / 1000, range)}</div>
      {payload.filter((p) => (p.value ?? 0) > 0).map((p) => (
        <div key={p.dataKey} className="flex items-center justify-between gap-4">
          <span className="flex items-center gap-1.5 text-slate-400">
            <span className="h-1.5 w-1.5 rounded-full" style={{ background: p.color }} />
            {p.name}
          </span>
          <span className="font-mono text-slate-100">{p.value}</span>
        </div>
      ))}
    </div>
  );
}
