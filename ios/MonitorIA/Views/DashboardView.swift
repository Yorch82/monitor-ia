import Foundation
import SwiftUI

// ============================================================================
// Dashboard principal adaptado al iPhone 16 Pro: KPIs, gráficas, contexto,
// hardware y coste energético en una sola columna táctil.
// ============================================================================

struct DashboardView: View {
    @EnvironmentObject private var store: MonitorStore

    var body: some View {
        ZStack {
            AppBackground()
            ScrollView {
                VStack(spacing: 14) {
                    BrandHeader(
                        connection: store.connection,
                        mode: store.snapshot?.mode,
                        serverHost: store.serverDisplay
                    )

                    if let snapshot = store.snapshot {
                        AlertBannerView(alerts: snapshot.alerts)
                        kpiGrid(snapshot)
                        TelemetryChartsPanel()
                        contextPanel(snapshot)
                        hardwareSection(snapshot)
                        costPanel(snapshot)
                        statusFooter(snapshot)
                    } else {
                        if let error = store.lastError {
                            offlinePanel(error)
                        }
                        loadingPanel
                    }
                }
                .padding(.horizontal, 16)
                .padding(.top, 8)
                .padding(.bottom, 30)
            }
            .scrollIndicators(.hidden)
            .refreshable {
                await store.refreshDashboard()
            }
        }
    }

    // MARK: - KPIs

    private func kpiGrid(_ snapshot: TelemetrySnapshot) -> some View {
        let tokens = snapshot.tokens
        let context = tokens.context
        let lastRequest = tokens.lastRequest

        return LazyVGrid(
            columns: [
                GridItem(.flexible(), spacing: 12),
                GridItem(.flexible(), spacing: 12),
            ],
            spacing: 12
        ) {
            KpiCard(
                title: "Tokens/s",
                value: Fmt.number(tokens.instantOutputPerS, maxDigits: 1),
                subtitle: "media \(Fmt.number(tokens.movingAvgOutputPerS, maxDigits: 1)) · entrada \(Fmt.number(tokens.instantInputPerS, maxDigits: 1))",
                systemImage: "speedometer",
                accent: Theme.green,
                footer: lastRequest.map { "última: \(Fmt.number($0.tokensPerSecond, maxDigits: 1)) t/s" } ?? "sin tráfico"
            )

            KpiCard(
                title: "Contexto",
                value: context.available ? Fmt.percent(context.percent, maxDigits: 1) : "—",
                subtitle: context.available
                    ? "\(Fmt.integer(context.usedTokens)) / \(Fmt.integer(context.maxTokens)) tokens"
                    : "Sin datos de contexto",
                systemImage: "gauge.medium",
                accent: levelColor(context.level),
                progress: context.percent,
                footer: context.available ? "fuente: \(context.source)" : nil
            )

            KpiCard(
                title: "GPU",
                value: Fmt.percent(snapshot.gpuAvgPct, maxDigits: 0),
                subtitle: snapshot.gpus.isEmpty
                    ? "Sin GPU detectada"
                    : "\(snapshot.gpus.count) GPU · \(Fmt.number(snapshot.gpuTempMaxC, maxDigits: 0)) ºC",
                systemImage: "cpu",
                accent: (snapshot.gpuTempMaxC ?? 0) >= 80 ? Theme.red : Theme.violet,
                progress: snapshot.gpuAvgPct,
                footer: snapshot.vramAvgPct.map { "VRAM \(Fmt.percent($0))" } ?? snapshot.hardware.gpuError
            )

            KpiCard(
                title: "Potencia",
                value: snapshot.power.currentW.map { "\(Fmt.number($0, maxDigits: 0)) W" } ?? "—",
                subtitle: snapshot.power.limitW.map {
                    "límite \(Fmt.number($0, maxDigits: 0)) W · \(Fmt.percent(snapshot.power.percent)) TDP"
                } ?? "Sin datos de potencia",
                systemImage: "bolt.fill",
                accent: Theme.amber,
                progress: snapshot.power.percent,
                footer: snapshot.power.available
                    ? "sesión \(Fmt.number(snapshot.power.energySessionKwh, maxDigits: 3)) kWh"
                    : nil
            )

            KpiCard(
                title: "Coste €/h",
                value: Fmt.euro(snapshot.cost.costPerHour),
                subtitle: "día \(Fmt.euro(snapshot.cost.projectionDay)) · mes \(Fmt.euro(snapshot.cost.projectionMonth))",
                systemImage: "eurosign.circle.fill",
                accent: Theme.deepBlue,
                footer: "sesión \(Fmt.euro(snapshot.cost.sessionCost, digits: 3)) · hoy \(Fmt.euro(snapshot.cost.dailyCost))"
            )

            KpiCard(
                title: "RAM",
                value: Fmt.percent(snapshot.system.ramPct),
                subtitle: snapshot.system.ramUsedGb.map {
                    "\(Fmt.number($0)) / \(Fmt.number(snapshot.system.ramTotalGb)) GB"
                } ?? "Sin datos",
                systemImage: "memorychip",
                accent: (snapshot.system.ramPct ?? 0) > 90 ? Theme.red : Theme.accent,
                progress: snapshot.system.ramPct,
                footer: snapshot.system.cpuPct.map { "CPU \(Fmt.percent($0))" }
            )
        }
    }

    // MARK: - Contexto

    private func contextPanel(_ snapshot: TelemetrySnapshot) -> some View {
        let context = snapshot.tokens.context
        let last = snapshot.tokens.lastRequest

        return Panel(title: "Ventana de contexto", systemImage: "gauge.medium") {
            if context.available {
                HStack(alignment: .lastTextBaseline) {
                    Text(Fmt.percent(context.percent, maxDigits: 1))
                        .font(.system(size: 34, weight: .semibold, design: .rounded))
                        .monospacedDigit()
                        .foregroundStyle(Theme.textPrimary)
                    Spacer()
                    LevelBadge(level: context.level)
                }
                UsageBar(percent: context.percent, color: levelColor(context.level), height: 8)
                HStack {
                    Text("\(Fmt.integer(context.usedTokens)) tokens usados")
                    Spacer()
                    Text("máx \(Fmt.integer(context.maxTokens))")
                }
                .font(.system(size: 9))
                .foregroundStyle(Theme.textMuted)
            } else {
                EmptyStateView(
                    icon: "text.alignleft",
                    title: "Sin ocupación de contexto",
                    message: "Necesita peticiones vía proxy o el modo simulación."
                )
            }

            if let last {
                Divider().overlay(Theme.border)
                Text("ÚLTIMA PETICIÓN")
                    .font(.system(size: 8, weight: .bold))
                    .tracking(0.8)
                    .foregroundStyle(Theme.textMuted)

                LazyVGrid(
                    columns: [GridItem(.flexible()), GridItem(.flexible())],
                    spacing: 7
                ) {
                    MiniMetric(label: "Entrada", value: Fmt.integer(last.inputTokens))
                    MiniMetric(label: "Salida", value: Fmt.integer(last.outputTokens))
                    MiniMetric(label: "Velocidad", value: "\(Fmt.number(last.tokensPerSecond, maxDigits: 1)) t/s")
                    MiniMetric(label: "Duración", value: String(format: "%.1f s", last.durationS))
                    MiniMetric(label: "Modelo", value: last.model ?? "—")
                    MiniMetric(label: "Hace", value: Fmt.relative(last.date))
                }
            }
        }
    }

    // MARK: - Hardware

    private func hardwareSection(_ snapshot: TelemetrySnapshot) -> some View {
        VStack(spacing: 12) {
            if snapshot.gpus.isEmpty {
                Panel(title: "GPU", systemImage: "cpu") {
                    EmptyStateView(
                        icon: "cpu",
                        title: "GPU sin datos",
                        message: snapshot.hardware.gpuError ?? "No hay proveedor de GPU disponible."
                    )
                }
            } else {
                ForEach(snapshot.gpus) { gpu in
                    GpuPanel(gpu: gpu)
                }
            }

            CompactGaugeCard(
                title: "Potencia eléctrica",
                systemImage: "bolt.fill",
                gaugeValue: snapshot.power.percent,
                gaugeLabel: "TDP",
                gaugeCenter: snapshot.power.currentW.map { "\(Fmt.number($0, maxDigits: 0)) W" },
                accent: Theme.amber
            ) {
                StatRow(label: "Consumo", value: snapshot.power.currentW.map { "\(Fmt.number($0, maxDigits: 0)) W" } ?? "—")
                StatRow(label: "Límite", value: snapshot.power.limitW.map { "\(Fmt.number($0, maxDigits: 0)) W" } ?? "—")
                StatRow(label: "Energía sesión", value: "\(Fmt.number(snapshot.power.energySessionWh, maxDigits: 0)) Wh")
            }

            CompactGaugeCard(
                title: "RAM del sistema",
                systemImage: "memorychip",
                gaugeValue: snapshot.system.ramPct,
                gaugeLabel: "RAM",
                gaugeCenter: Fmt.percent(snapshot.system.ramPct),
                accent: Theme.accent
            ) {
                StatRow(label: "Usada", value: Fmt.gigabytesFromGB(snapshot.system.ramUsedGb))
                StatRow(label: "Total", value: Fmt.gigabytesFromGB(snapshot.system.ramTotalGb))
                StatRow(label: "CPU", value: Fmt.percent(snapshot.system.cpuPct))
                StatRow(label: "Swap", value: Fmt.percent(snapshot.system.swapPct))
            }
        }
    }

    // MARK: - Coste

    private func costPanel(_ snapshot: TelemetrySnapshot) -> some View {
        let cost = snapshot.cost
        return Panel(title: "Coste energético", systemImage: "eurosign.circle.fill") {
            HStack(spacing: 10) {
                costBox(label: "Sesión", value: Fmt.euro(cost.sessionCost, digits: 3))
                costBox(label: "Hoy", value: Fmt.euro(cost.dailyCost))
            }

            Text("PROYECCIÓN AL RITMO ACTUAL")
                .font(.system(size: 8, weight: .bold))
                .tracking(0.8)
                .foregroundStyle(Theme.textMuted)

            HStack(spacing: 8) {
                projectionBox("Hora", Fmt.euro(cost.costPerHour))
                projectionBox("Día", Fmt.euro(cost.projectionDay))
                projectionBox("Mes", Fmt.euro(cost.projectionMonth))
            }

            HStack {
                Text("Coste / 1.000 tokens")
                    .font(.system(size: 10))
                    .foregroundStyle(Theme.textSecondary)
                Spacer()
                Text(Fmt.euro(cost.costPer1kTokens, digits: 4))
                    .font(.system(size: 13, weight: .semibold, design: .monospaced))
                    .foregroundStyle(Theme.textPrimary)
            }

            if let limit = cost.dailyLimit, limit > 0 {
                Divider().overlay(Theme.border)
                HStack {
                    Text("Presupuesto diario · \(Fmt.euro(limit))")
                    Spacer()
                    Text(Fmt.percent(cost.dailyPct))
                }
                .font(.system(size: 9))
                .foregroundStyle(Theme.textMuted)
                UsageBar(
                    percent: cost.dailyPct,
                    color: (cost.dailyPct ?? 0) > 100 ? Theme.red : Theme.amber,
                    height: 4
                )
            }
        }
    }

    // MARK: - Estados

    private var loadingPanel: some View {
        Panel(title: "Conectando", systemImage: "antenna.radiowaves.left.and.right") {
            HStack(spacing: 10) {
                ProgressView()
                    .tint(Theme.accent)
                VStack(alignment: .leading, spacing: 3) {
                    Text("Esperando telemetría…")
                        .font(.system(size: 12, weight: .medium))
                        .foregroundStyle(Theme.textSecondary)
                    Text(store.serverURL)
                        .font(.system(size: 9, design: .monospaced))
                        .foregroundStyle(Theme.textMuted)
                        .lineLimit(1)
                }
                Spacer()
            }
            Button("Reintentar") {
                Task { await store.refreshDashboard() }
            }
            .buttonStyle(GhostButtonStyle())
        }
    }

    private func offlinePanel(_ message: String) -> some View {
        Panel(title: "Sin conexión", systemImage: "wifi.exclamationmark") {
            Text(message)
                .font(.system(size: 11))
                .foregroundStyle(Theme.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
            Text("Revisa la URL en Ajustes: LAN `http://192.168.1.35:8080` o VPN `http://100.115.55.87:8080`.")
                .font(.system(size: 9))
                .foregroundStyle(Theme.textMuted)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    private func statusFooter(_ snapshot: TelemetrySnapshot) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text("IA · \(snapshot.inference.status.rawValue.uppercased())")
                    .foregroundStyle(snapshot.inference.status == .online ? Theme.green : Theme.red)
                Spacer()
                Text("intervalo \(Fmt.number(snapshot.intervalS, maxDigits: 1)) s")
            }
            HStack {
                Text("\(snapshot.inference.engine.isEmpty ? "openai-compat" : snapshot.inference.engine) · \(snapshot.inference.model)")
                    .lineLimit(1)
                Spacer()
                if let latency = snapshot.inference.latencyMs {
                    Text(Fmt.milliseconds(latency))
                }
            }
            if let hint = snapshot.inference.contextHintTokens, snapshot.inference.contextHintSource != "simulation" {
                Text("ventana detectada: \(Fmt.integer(hint)) tokens (\(snapshot.inference.contextHintSource))")
            }
        }
        .font(.system(size: 9))
        .foregroundStyle(Theme.textMuted)
        .padding(.horizontal, 4)
        .padding(.top, 4)
    }

    // MARK: - Helpers visuales

    private func levelColor(_ level: ContextLevel) -> Color {
        switch level {
        case .ok: return Theme.green
        case .warning: return Theme.amber
        case .critical: return Theme.red
        case .unavailable: return Theme.textMuted
        }
    }

    private func costBox(label: String, value: String) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(label.uppercased())
                .font(.system(size: 8, weight: .bold))
                .tracking(0.6)
                .foregroundStyle(Theme.textMuted)
            Text(value)
                .font(.system(size: 18, weight: .semibold, design: .rounded))
                .monospacedDigit()
                .foregroundStyle(Theme.textPrimary)
                .lineLimit(1)
                .minimumScaleFactor(0.7)
        }
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .fill(Theme.backgroundSecondary)
        )
        .overlay(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .stroke(Theme.border, lineWidth: 1)
        )
    }

    private func projectionBox(_ label: String, _ value: String) -> some View {
        VStack(spacing: 2) {
            Text(label.uppercased())
                .font(.system(size: 8, weight: .bold))
                .tracking(0.6)
                .foregroundStyle(Theme.textMuted)
            Text(value)
                .font(.system(size: 12, weight: .semibold, design: .rounded))
                .monospacedDigit()
                .foregroundStyle(Theme.textPrimary)
                .lineLimit(1)
                .minimumScaleFactor(0.7)
        }
        .padding(.vertical, 8)
        .frame(maxWidth: .infinity)
        .background(
            RoundedRectangle(cornerRadius: 10, style: .continuous)
                .fill(Theme.backgroundSecondary)
        )
    }
}

// MARK: - Subcomponentes

private struct GpuPanel: View {
    let gpu: GpuReading

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 6) {
                Image(systemName: "cpu")
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(Theme.violet)
                VStack(alignment: .leading, spacing: 1) {
                    Text(gpu.name)
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundStyle(Theme.textPrimary)
                        .lineLimit(1)
                    Text("GPU \(gpu.index) · \(gpu.vendor.uppercased())")
                        .font(.system(size: 8))
                        .tracking(0.5)
                        .foregroundStyle(Theme.textMuted)
                }
                Spacer()
                if let temperature = gpu.temperatureC {
                    Text("\(Fmt.number(temperature, maxDigits: 0)) ºC")
                        .font(.system(size: 10, weight: .semibold, design: .monospaced))
                        .foregroundStyle(temperature >= 80 ? Theme.red : Theme.textSecondary)
                }
            }

            HStack(alignment: .center, spacing: 10) {
                RingGauge(value: gpu.utilizationPct, label: "uso", size: 96)

                VStack(spacing: 5) {
                    StatRow(
                        label: "VRAM",
                        value: "\(Fmt.gigabytes(gpu.memoryUsedMb)) / \(Fmt.gigabytes(gpu.memoryTotalMb))"
                    )
                    UsageBar(
                        percent: gpu.memoryPct,
                        color: (gpu.memoryPct ?? 0) > 95 ? Theme.red : Theme.violet,
                        height: 4
                    )
                    StatRow(
                        label: "Temperatura",
                        value: gpu.temperatureC.map { "\(Fmt.number($0, maxDigits: 0)) ºC" } ?? "—",
                        highlight: (gpu.temperatureC ?? 0) >= 80
                    )
                    StatRow(
                        label: "Ventilador",
                        value: gpu.fanPct.map { Fmt.percent($0) } ?? "—"
                    )
                    StatRow(
                        label: "Potencia",
                        value: "\(Fmt.number(gpu.powerW, maxDigits: 0)) / \(Fmt.number(gpu.powerLimitW, maxDigits: 0)) W"
                    )
                }
                .frame(maxWidth: .infinity)
            }
        }
        .padding(14)
        .cardStyle()
    }
}

private struct MiniMetric: View {
    let label: String
    let value: String

    var body: some View {
        HStack(spacing: 4) {
            Text(label)
                .font(.system(size: 9))
                .foregroundStyle(Theme.textMuted)
            Spacer(minLength: 2)
            Text(value)
                .font(.system(size: 9, weight: .medium, design: .monospaced))
                .foregroundStyle(Theme.textSecondary)
                .lineLimit(1)
        }
    }
}

private struct LevelBadge: View {
    let level: ContextLevel

    private var label: String {
        switch level {
        case .ok: return "SALUDABLE"
        case .warning: return "ALTO"
        case .critical: return "CRÍTICO"
        case .unavailable: return "SIN DATOS"
        }
    }

    private var color: Color {
        switch level {
        case .ok: return Theme.green
        case .warning: return Theme.amber
        case .critical: return Theme.red
        case .unavailable: return Theme.textMuted
        }
    }

    var body: some View {
        Text(label)
            .font(.system(size: 8, weight: .bold))
            .tracking(0.6)
            .foregroundStyle(color)
            .padding(.horizontal, 7)
            .padding(.vertical, 3)
            .background(Capsule().fill(color.opacity(0.12)))
    }
}
