/** Gráficas concretas del dashboard (tokens, recursos, potencia). */

import { useMonitor } from "../../state/MonitorContext";
import type { ChartPoint, Range } from "../../types/telemetry";
import { Card } from "../ui/Card";
import { DashboardChart, type SeriesDef } from "./DashboardChart";
import { IconActivity, IconBolt, IconCpu } from "../Icons";

const TOKEN_SERIES: SeriesDef[] = [
  { key: "input_per_s", label: "Entrada (t/s)", color: "#38bdf8" },
  { key: "output_per_s", label: "Salida (t/s)", color: "#34d399" },
  { key: "moving_avg_per_s", label: "Media móvil salida", color: "#fbbf24", dashed: true },
];

const RESOURCE_SERIES: SeriesDef[] = [
  { key: "gpu_pct", label: "GPU %", color: "#22d3ee" },
  { key: "vram_pct", label: "VRAM %", color: "#a78bfa" },
  { key: "ram_pct", label: "RAM %", color: "#f472b6" },
  { key: "cpu_pct", label: "CPU %", color: "#facc15" },
];

const POWER_SERIES: SeriesDef[] = [{ key: "power_w", label: "Potencia (W)", color: "#fb923c" }];

export function TokensChart() {
  const { points, range, setRange } = useMonitor();
  return (
    <Card title="Throughput de tokens" icon={<IconActivity className="h-4 w-4" />}>
      <Chart points={points} range={range} onRangeChange={setRange} series={TOKEN_SERIES} />
    </Card>
  );
}

export function ResourcesChart() {
  const { points, range, setRange } = useMonitor();
  return (
    <Card title="Recursos del sistema" icon={<IconCpu className="h-4 w-4" />}>
      <Chart points={points} range={range} onRangeChange={setRange} series={RESOURCE_SERIES} yDomain={[0, 100]} unitSuffix="%" />
    </Card>
  );
}

export function PowerChart() {
  const { points, range, setRange } = useMonitor();
  return (
    <Card title="Potencia" icon={<IconBolt className="h-4 w-4" />}>
      <Chart points={points} range={range} onRangeChange={setRange} series={POWER_SERIES} unitSuffix=" W" />
    </Card>
  );
}

function Chart({
  points,
  range,
  onRangeChange,
  series,
  yDomain,
  unitSuffix,
}: {
  points: ChartPoint[];
  range: Range;
  onRangeChange: (r: Range) => void;
  series: SeriesDef[];
  yDomain?: [number | string, number | string];
  unitSuffix?: string;
}) {
  if (points.length === 0) {
    return (
      <div className="flex h-[240px] flex-col items-center justify-center gap-1 text-sm text-slate-500">
        <span className="font-mono text-2xl text-slate-700">—</span>
        Sin datos todavía…
      </div>
    );
  }
  return <DashboardChart points={points} range={range} series={series} yDomain={yDomain} onRangeChange={onRangeChange} unitSuffix={unitSuffix} />;
}
