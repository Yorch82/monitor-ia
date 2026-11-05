/** Contexto global de telemetría: WebSocket + histórico + settings compartidos. */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import type { ChartPoint, Range, TelemetrySnapshot } from "../types/telemetry";
import { fetchHistory, fetchSnapshot, wsUrl } from "../lib/api";
import { RANGE_MS, normalizeHistory, snapshotToPoint } from "../lib/points";

type ConnState = "connecting" | "live" | "reconnecting" | "offline";

interface MonitorState {
  snapshot: TelemetrySnapshot | null;
  points: ChartPoint[];
  range: Range;
  setRange: (r: Range) => void;
  connection: ConnState;
  lastError: string | null;
}

const MonitorContext = createContext<MonitorState | null>(null);

const RANGE_MS_LOCAL = RANGE_MS;

export function MonitorProvider({ children }: { children: ReactNode }) {
  const [snapshot, setSnapshot] = useState<TelemetrySnapshot | null>(null);
  const [points, setPoints] = useState<ChartPoint[]>([]);
  const [range, setRangeState] = useState<Range>("15m");
  const [connection, setConnection] = useState<ConnState>("connecting");
  const [lastError, setLastError] = useState<string | null>(null);

  const rangeRef = useRef(range);
  rangeRef.current = range;

  // ── histórico (al cargar o cambiar de rango) ─────────────────────────────
  const loadHistory = useCallback(async () => {
    try {
      const data = await fetchHistory(rangeRef.current);
      setPoints(normalizeHistory(data.points));
      setLastError(null);
    } catch (err) {
      setLastError(err instanceof Error ? err.message : "Error cargando histórico");
    }
  }, []);

  useEffect(() => {
    void loadHistory();
  }, [range, loadHistory]);

  // ── snapshot inicial por HTTP (antes de que llegue el primer frame WS) ───
  useEffect(() => {
    let alive = true;
    fetchSnapshot()
      .then((d) => {
        if (alive && d.snapshot) setSnapshot(d.snapshot);
      })
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, []);

  // ── WebSocket con reconexión exponencial ─────────────────────────────────
  useEffect(() => {
    let ws: WebSocket | null = null;
    let closed = false;
    let attempt = 0;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;

    const connect = () => {
      if (closed) return;
      try {
        ws = new WebSocket(wsUrl());
      } catch {
        scheduleRetry();
        return;
      }
      ws.onopen = () => {
        attempt = 0;
        setConnection("live");
        setLastError(null);
        void loadHistory(); // rellena huecos tras reconectar
      };
      ws.onmessage = (ev) => {
        try {
          const snap = JSON.parse(ev.data as string) as TelemetrySnapshot;
          setSnapshot(snap);
          appendPoint(snap);
        } catch {
          /* frame corrupto: se ignora */
        }
      };
      ws.onerror = () => {
        setLastState();
      };
      ws.onclose = () => {
        setLastState();
        scheduleRetry();
      };
    };

    const setLastState = () => {
      setConnection((prev) => (prev === "offline" || closed ? prev : "reconnecting"));
    };

    const scheduleRetry = () => {
      if (closed) return;
      setConnection(attempt >= 2 ? "offline" : "reconnecting");
      setLastError("Sin conexión con el backend");
      const delay = Math.min(10_000, 600 * Math.pow(1.8, attempt++));
      retryTimer = setTimeout(connect, delay);
    };

    const appendPoint = (snap: TelemetrySnapshot) => {
      const point = snapshotToPoint(snap);
      setPoints((prev) => {
        const next = prev.length && prev[prev.length - 1].t >= point.t ? prev.slice(0, -1) : prev;
        const windowStart = point.t - RANGE_MS_LOCAL[rangeRef.current];
        const trimmed = next.filter((p) => p.t >= windowStart);
        trimmed.push(point);
        return trimmed;
      });
    };

    connect();
    return () => {
      closed = true;
      if (retryTimer) clearTimeout(retryTimer);
      ws?.close();
    };
  }, [loadHistory]);

  const setRange = useCallback((r: Range) => setRangeState(r), []);

  const value = useMemo<MonitorState>(
    () => ({ snapshot, points, range, setRange, connection, lastError }),
    [snapshot, points, range, setRange, connection, lastError],
  );

  return <MonitorContext.Provider value={value}>{children}</MonitorContext.Provider>;
}

export function useMonitor(): MonitorState {
  const ctx = useContext(MonitorContext);
  if (!ctx) throw new Error("useMonitor debe usarse dentro de <MonitorProvider>");
  return ctx;
}
