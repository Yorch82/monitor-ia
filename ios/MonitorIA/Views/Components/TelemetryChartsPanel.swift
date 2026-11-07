import Charts
import SwiftUI

// ============================================================================
// Panel de gráficas del dashboard con Swift Charts nativo y selector de métrica.
// ============================================================================

enum DashboardChartMetric: String, CaseIterable, Identifiable {
    case tokens = "Tokens"
    case resources = "Recursos"
    case power = "Potencia"

    var id: String { rawValue }
}

struct TelemetryChartsPanel: View {
    @EnvironmentObject private var store: MonitorStore
    @State private var metric: DashboardChartMetric = .tokens

    var body: some View {
        Panel(
            title: "Actividad en tiempo real",
            systemImage: "chart.xyaxis.line",
            trailing: AnyView(rangeMenu)
        ) {
            Picker("Métrica", selection: $metric) {
                ForEach(DashboardChartMetric.allCases) { item in
                    Text(item.rawValue).tag(item)
                }
            }
            .pickerStyle(.segmented)
            .tint(Theme.accent)

            if store.points.isEmpty {
                EmptyStateView(
                    icon: "waveform.path.ecg",
                    title: "Esperando telemetría",
                    message: "La gráfica se dibujará en cuanto llegue el primer frame del servidor."
                )
                .frame(height: 220)
            } else {
                chart
            }

            HStack(spacing: 12) {
                ForEach(legendItems.indices, id: \.self) { index in
                    let item = legendItems[index]
                    HStack(spacing: 4) {
                        Circle()
                            .fill(item.1)
                            .frame(width: 5, height: 5)
                        Text(item.0)
                            .font(.system(size: 9))
                            .foregroundStyle(Theme.textMuted)
                    }
                }
                Spacer()
            }        }
    }

    // MARK: - Menú de rango

    private var rangeMenu: some View {
        Menu {
            ForEach(ChartRange.allCases) { range in
                Button {
                    store.setRange(range)
                } label: {
                    if store.range == range {
                        Label(range.shortLabel, systemImage: "checkmark")
                    } else {
                        Text(range.shortLabel)
                    }
                }
            }
        } label: {
            HStack(spacing: 4) {
                Text(store.range.shortLabel)
                Image(systemName: "chevron.down")
                    .font(.system(size: 8, weight: .bold))
            }
            .font(.system(size: 10, weight: .semibold))
            .foregroundStyle(Theme.textSecondary)
            .padding(.horizontal, 8)
            .padding(.vertical, 5)
            .background(Capsule().fill(Color.white.opacity(0.04)))
            .overlay(Capsule().stroke(Theme.border, lineWidth: 1))
        }
    }

    // MARK: - Series

    private struct LineSample: Identifiable {
        let id: Int
        let date: Date
        let value: Double
    }

    private func samples(_ keyPath: KeyPath<ChartPoint, Double?>) -> [LineSample] {
        store.points.compactMap { point in
            guard let value = point[keyPath: keyPath], value.isFinite else { return nil }
            return LineSample(id: point.t, date: point.date, value: value)
        }
    }

    private var legendItems: [(String, Color)] {
        switch metric {
        case .tokens:
            return [
                ("Entrada t/s", Theme.blue),
                ("Salida t/s", Theme.green),
                ("Media móvil", Theme.amber),
            ]
        case .resources:
            return [
                ("GPU", Theme.accent),
                ("VRAM", Theme.violet),
                ("RAM", Theme.pink),
                ("CPU", Theme.yellow),
            ]
        case .power:
            return [("Potencia W", Theme.orange)]
        }
    }

    // MARK: - Chart

    @ViewBuilder
    private var chart: some View {
        switch metric {
        case .tokens:
            tokensChart
        case .resources:
            resourcesChart
        case .power:
            powerChart
        }
    }

    private var tokensChart: some View {
        styledChart(yMax: tokensYMax, usesPercentAxis: false) {
            Chart {
                ForEach(samples(\.inputPerS)) { sample in
                    LineMark(
                        x: .value("Hora", sample.date),
                        y: .value("Entrada", sample.value)
                    )
                    .foregroundStyle(Theme.blue)
                    .lineStyle(StrokeStyle(lineWidth: 1.8))
                    .interpolationMethod(.catmullRom)
                }
                ForEach(samples(\.outputPerS)) { sample in
                    LineMark(
                        x: .value("Hora", sample.date),
                        y: .value("Salida", sample.value)
                    )
                    .foregroundStyle(Theme.green)
                    .lineStyle(StrokeStyle(lineWidth: 1.8))
                    .interpolationMethod(.catmullRom)
                }
                ForEach(samples(\.movingAvgPerS)) { sample in
                    LineMark(
                        x: .value("Hora", sample.date),
                        y: .value("Media", sample.value)
                    )
                    .foregroundStyle(Theme.amber)
                    .lineStyle(StrokeStyle(lineWidth: 1.4, dash: [4, 3]))
                    .interpolationMethod(.catmullRom)
                }
            }
            .chartLegend(.hidden)
        }
    }

    private var resourcesChart: some View {
        styledChart(yMax: 100, usesPercentAxis: true) {
            Chart {
                ForEach(samples(\.gpuPct)) { sample in
                    LineMark(x: .value("Hora", sample.date), y: .value("GPU", sample.value))
                        .foregroundStyle(Theme.accent)
                        .lineStyle(StrokeStyle(lineWidth: 1.7))
                }
                ForEach(samples(\.vramPct)) { sample in
                    LineMark(x: .value("Hora", sample.date), y: .value("VRAM", sample.value))
                        .foregroundStyle(Theme.violet)
                        .lineStyle(StrokeStyle(lineWidth: 1.7))
                }
                ForEach(samples(\.ramPct)) { sample in
                    LineMark(x: .value("Hora", sample.date), y: .value("RAM", sample.value))
                        .foregroundStyle(Theme.pink)
                        .lineStyle(StrokeStyle(lineWidth: 1.7))
                }
                ForEach(samples(\.cpuPct)) { sample in
                    LineMark(x: .value("Hora", sample.date), y: .value("CPU", sample.value))
                        .foregroundStyle(Theme.yellow)
                        .lineStyle(StrokeStyle(lineWidth: 1.4))
                }
            }
            .chartLegend(.hidden)
        }
    }

    private var powerChart: some View {
        styledChart(yMax: powerYMax, usesPercentAxis: false) {
            Chart {
                ForEach(samples(\.powerW)) { sample in
                    AreaMark(
                        x: .value("Hora", sample.date),
                        y: .value("Potencia", sample.value)
                    )
                    .interpolationMethod(.catmullRom)
                    .foregroundStyle(
                        LinearGradient(
                            colors: [Theme.orange.opacity(0.35), Theme.orange.opacity(0.02)],
                            startPoint: .top,
                            endPoint: .bottom
                        )
                    )
                    LineMark(
                        x: .value("Hora", sample.date),
                        y: .value("Potencia", sample.value)
                    )
                    .foregroundStyle(Theme.orange)
                    .lineStyle(StrokeStyle(lineWidth: 1.8))
                }
            }
            .chartLegend(.hidden)
        }
    }

    // MARK: - Estilos

    private var xDomain: ClosedRange<Date> {
        let end = store.points.last?.date ?? Date()
        let start = end.addingTimeInterval(-store.range.seconds)
        return start...end
    }

    private var tokensYMax: Double {
        let values = store.points
            .flatMap { [$0.inputPerS, $0.outputPerS, $0.movingAvgPerS] }
            .compactMap { $0 }
        let maxValue = values.max() ?? 10
        return max(10, ceil(maxValue * 1.15 / 10) * 10)
    }

    private var powerYMax: Double {
        let dataMax = store.points.compactMap(\.powerW).max() ?? 0
        let limit = store.snapshot?.power.limitW ?? 0
        let maxValue = max(dataMax, limit, 100)
        return ceil(maxValue * 1.12 / 50) * 50
    }

    private func styledChart<Content: View>(
        yMax: Double,
        usesPercentAxis: Bool,
        @ViewBuilder content: () -> Content
    ) -> some View {
        content()
            .frame(height: 220)
            .chartXScale(domain: xDomain)
            .chartYScale(domain: 0...max(1, yMax))
            .chartXAxis {
                AxisMarks(values: .automatic(desiredCount: 4)) { value in
                    AxisGridLine(stroke: StrokeStyle(lineWidth: 0.5))
                        .foregroundStyle(Theme.border)
                    AxisValueLabel {
                        if let date = value.as(Date.self) {
                            Text(Fmt.time(date, range: store.range))
                                .font(.system(size: 8))
                                .foregroundStyle(Theme.textMuted)
                        }
                    }
                }
            }
            .chartYAxis {
                AxisMarks(position: .leading, values: .automatic(desiredCount: 3)) { value in
                    AxisGridLine(stroke: StrokeStyle(lineWidth: 0.5))
                        .foregroundStyle(Theme.border)
                    AxisValueLabel {
                        if let doubleValue = value.as(Double.self) {
                            Text(usesPercentAxis
                                 ? "\(Int(doubleValue))%"
                                 : Fmt.number(doubleValue, maxDigits: 0))
                                .font(.system(size: 8))
                                .foregroundStyle(Theme.textMuted)
                        }
                    }
                }
            }
    }
}
