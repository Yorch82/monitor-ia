import SwiftUI
import UIKit

// ============================================================================
// Componentes de UI compartidos (tarjetas, cabecera, chips, badges…).
// ============================================================================

// MARK: - Cabecera de pantalla

struct ScreenHeader<Trailing: View>: View {
    let title: String
    let subtitle: String
    let systemImage: String
    let accent: Color
    let trailing: Trailing

    init(
        title: String,
        subtitle: String,
        systemImage: String,
        accent: Color = Theme.accent,
        @ViewBuilder trailing: () -> Trailing
    ) {
        self.title = title
        self.subtitle = subtitle
        self.systemImage = systemImage
        self.accent = accent
        self.trailing = trailing()
    }

    var body: some View {
        HStack(spacing: 12) {
            ZStack {
                RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .fill(accent.opacity(0.12))
                Image(systemName: systemImage)
                    .font(.system(size: 18, weight: .semibold))
                    .foregroundStyle(accent)
            }
            .frame(width: 40, height: 40)

            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(.system(size: 18, weight: .bold))
                    .foregroundStyle(Theme.textPrimary)
                Text(subtitle)
                    .font(.system(size: 10))
                    .foregroundStyle(Theme.textMuted)
                    .lineLimit(1)
            }
            Spacer(minLength: 8)
            trailing
        }
    }
}

extension ScreenHeader where Trailing == EmptyView {
    init(title: String, subtitle: String, systemImage: String, accent: Color = Theme.accent) {
        self.init(title: title, subtitle: subtitle, systemImage: systemImage, accent: accent) {
            EmptyView()
        }
    }
}

// MARK: - Marca + estado

struct BrandHeader: View {
    let connection: ConnectionState
    let mode: TelemetryMode?
    let serverHost: String

    var body: some View {
        HStack(spacing: 12) {
            ZStack {
                RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .fill(
                        LinearGradient(
                            colors: [Theme.accent.opacity(0.9), Theme.deepBlue.opacity(0.9)],
                            startPoint: .topLeading,
                            endPoint: .bottomTrailing
                        )
                    )
                Image(systemName: "waveform.path.ecg")
                    .font(.system(size: 20, weight: .bold))
                    .foregroundStyle(Color(hex: 0x05070D))
            }
            .frame(width: 42, height: 42)
            .shadow(color: Theme.accent.opacity(0.35), radius: 10, x: 0, y: 4)

            VStack(alignment: .leading, spacing: 2) {
                Text("MONITOR IA")
                    .font(.system(size: 15, weight: .bold))
                    .tracking(1.2)
                    .foregroundStyle(Theme.textPrimary)
                Text(serverHost)
                    .font(.system(size: 10))
                    .foregroundStyle(Theme.textMuted)
                    .lineLimit(1)
            }

            Spacer(minLength: 4)

            VStack(alignment: .trailing, spacing: 4) {
                ConnectionBadge(state: connection)
                if let mode {
                    ModeBadge(mode: mode)
                }
            }
        }
    }
}

struct ConnectionBadge: View {
    let state: ConnectionState

    private var color: Color {
        switch state {
        case .live: return Theme.green
        case .connecting: return Theme.textMuted
        case .reconnecting: return Theme.amber
        case .offline: return Theme.red
        }
    }

    var body: some View {
        HStack(spacing: 5) {
            Circle()
                .fill(color)
                .frame(width: 6, height: 6)
                .opacity(state == .live ? 1 : 0.8)
            Text(state.label)
                .font(.system(size: 8, weight: .bold))
                .tracking(0.6)
        }
        .foregroundStyle(color)
        .padding(.horizontal, 8)
        .padding(.vertical, 4)
        .background(Capsule().fill(color.opacity(0.10)))
        .overlay(Capsule().stroke(color.opacity(0.30), lineWidth: 1))
    }
}

struct ModeBadge: View {
    let mode: TelemetryMode

    private var color: Color { mode == .simulation ? Theme.violet : Theme.green }
    private var label: String { mode == .simulation ? "SIMULACIÓN" : "LIVE" }

    var body: some View {
        Text(label)
            .font(.system(size: 8, weight: .bold))
            .tracking(0.8)
            .foregroundStyle(color)
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
            .background(Capsule().fill(color.opacity(0.10)))
            .overlay(Capsule().stroke(color.opacity(0.30), lineWidth: 1))
    }
}

// MARK: - Panel y KPI

struct Panel<Content: View>: View {
    let title: String?
    let systemImage: String?
    let trailing: AnyView?
    let content: Content

    init(
        title: String? = nil,
        systemImage: String? = nil,
        trailing: AnyView? = nil,
        @ViewBuilder content: () -> Content
    ) {
        self.title = title
        self.systemImage = systemImage
        self.trailing = trailing
        self.content = content()
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            if title != nil || trailing != nil {
                HStack(spacing: 6) {
                    if let systemImage {
                        Image(systemName: systemImage)
                            .font(.system(size: 11, weight: .semibold))
                            .foregroundStyle(Theme.accent)
                    }
                    if let title {
                        Text(title.uppercased())
                            .font(.system(size: 9, weight: .bold))
                            .tracking(1.1)
                            .foregroundStyle(Theme.textMuted)
                    }
                    Spacer()
                    if let trailing {
                        trailing
                    }
                }
            }
            content
        }
        .padding(14)
        .cardStyle()
    }
}

struct KpiCard: View {
    let title: String
    let value: String
    var subtitle: String? = nil
    let systemImage: String
    var accent: Color = Theme.accent
    var progress: Double? = nil
    var footer: String? = nil

    var body: some View {
        VStack(alignment: .leading, spacing: 7) {
            HStack(alignment: .center) {
                Text(title.uppercased())
                    .font(.system(size: 8, weight: .bold))
                    .tracking(0.9)
                    .foregroundStyle(Theme.textMuted)
                Spacer(minLength: 4)
                Image(systemName: systemImage)
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(accent)
            }

            Text(value)
                .font(.system(size: 23, weight: .semibold, design: .rounded))
                .monospacedDigit()
                .foregroundStyle(Theme.textPrimary)
                .lineLimit(1)
                .minimumScaleFactor(0.65)

            if let subtitle {
                Text(subtitle)
                    .font(.system(size: 9))
                    .foregroundStyle(Theme.textSecondary)
                    .lineLimit(2)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }

            if let progress {
                UsageBar(percent: progress, color: accent, height: 3)
            }

            Spacer(minLength: 0)

            if let footer {
                Text(footer)
                    .font(.system(size: 8))
                    .foregroundStyle(Theme.textMuted)
                    .lineLimit(1)
            }
        }
        .padding(12)
        .frame(maxWidth: .infinity, minHeight: 122, alignment: .topLeading)
        .cardStyle(accent: accent.opacity(0.5))
    }
}

struct UsageBar: View {
    let percent: Double?
    var color: Color = Theme.accent
    var height: CGFloat = 5

    var body: some View {
        GeometryReader { proxy in
            ZStack(alignment: .leading) {
                Capsule().fill(Color.white.opacity(0.06))
                Capsule()
                    .fill(color)
                    .frame(
                        width: proxy.size.width
                            * CGFloat(max(0, min(100, percent ?? 0)) / 100.0)
                    )
            }
        }
        .frame(height: height)
        .animation(.easeInOut(duration: 0.35), value: percent)
    }
}

struct StatRow: View {
    let label: String
    let value: String
    var highlight: Bool = false

    var body: some View {
        HStack(spacing: 6) {
            Text(label)
                .font(.system(size: 10))
                .foregroundStyle(Theme.textMuted)
            Spacer(minLength: 6)
            Text(value)
                .font(.system(size: 10, weight: .medium, design: .monospaced))
                .foregroundStyle(highlight ? Theme.amber : Theme.textSecondary)
                .lineLimit(1)
                .minimumScaleFactor(0.8)
        }
    }
}

struct EmptyStateView: View {
    let icon: String
    let title: String
    let message: String

    var body: some View {
        VStack(spacing: 8) {
            Image(systemName: icon)
                .font(.system(size: 24, weight: .light))
                .foregroundStyle(Theme.textMuted.opacity(0.6))
            Text(title)
                .font(.system(size: 13, weight: .semibold))
                .foregroundStyle(Theme.textSecondary)
            Text(message)
                .font(.system(size: 10))
                .foregroundStyle(Theme.textMuted)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 28)
    }
}

// MARK: - Alertas

struct AlertBannerView: View {
    let alerts: [AlertItem]

    private var isCritical: Bool {
        alerts.contains { $0.severity == .critical }
    }
    private var color: Color { isCritical ? Theme.red : Theme.amber }

    var body: some View {
        Group {
            if let first = alerts.first {
                HStack(alignment: .top, spacing: 10) {
                    Image(systemName: "exclamationmark.triangle.fill")
                        .font(.system(size: 13))
                        .foregroundStyle(color)
                    VStack(alignment: .leading, spacing: 2) {
                        Text(first.message)
                            .font(.system(size: 11, weight: .medium))
                            .foregroundStyle(color)
                            .lineLimit(2)
                        if alerts.count > 1 {
                            Text("+\(alerts.count - 1) alerta\(alerts.count - 1 == 1 ? "" : "s") más")
                                .font(.system(size: 9))
                                .foregroundStyle(color.opacity(0.75))
                        }
                    }
                    Spacer(minLength: 0)
                }
                .padding(12)
                .background(
                    RoundedRectangle(cornerRadius: 14, style: .continuous)
                        .fill(color.opacity(0.10))
                )
                .overlay(
                    RoundedRectangle(cornerRadius: 14, style: .continuous)
                        .stroke(color.opacity(0.35), lineWidth: 1)
                )
            }
        }
    }
}

// MARK: - Seguridad

struct SourceChip: View {
    let label: String
    let isOn: Bool
    var isNeutral: Bool = false

    private var color: Color {
        if isNeutral { return Theme.textMuted }
        return isOn ? Theme.green : Theme.amber
    }

    var body: some View {
        HStack(spacing: 5) {
            Circle().fill(color).frame(width: 5, height: 5)
            Text(label.uppercased())
                .font(.system(size: 8, weight: .bold))
                .tracking(0.5)
        }
        .foregroundStyle(color)
        .padding(.horizontal, 8)
        .padding(.vertical, 5)
        .background(Capsule().fill(color.opacity(0.10)))
        .overlay(Capsule().stroke(color.opacity(0.25), lineWidth: 1))
    }
}

struct ClassificationBadge: View {
    let classification: SecurityClassification

    private var label: String {
        switch classification {
        case .bot: return "BOT"
        case .human: return "HUMANO"
        case .unknown: return "DESCONOCIDO"
        }
    }

    private var color: Color {
        switch classification {
        case .bot: return Theme.red
        case .human: return Theme.green
        case .unknown: return Theme.textMuted
        }
    }

    var body: some View {
        Text(label)
            .font(.system(size: 8, weight: .bold))
            .tracking(0.4)
            .foregroundStyle(color)
            .padding(.horizontal, 6)
            .padding(.vertical, 3)
            .background(Capsule().fill(color.opacity(0.12)))
            .overlay(Capsule().stroke(color.opacity(0.3), lineWidth: 1))
    }
}

struct ThreatList: View {
    let title: String
    let icon: String
    let rows: [(String, Int)]
    let emptyText: String

    private var maxValue: Int { max(rows.map { $0.1 }.max() ?? 1, 1) }
    private var topRows: [(String, Int)] { Array(rows.prefix(4)) }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 5) {
                Image(systemName: icon)
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundStyle(Theme.accent)
                Text(title.uppercased())
                    .font(.system(size: 8, weight: .bold))
                    .tracking(0.8)
                    .foregroundStyle(Theme.textMuted)
            }
            if rows.isEmpty {
                Text(emptyText)
                    .font(.system(size: 9))
                    .foregroundStyle(Theme.textMuted)
                    .padding(.vertical, 4)
            } else {
                ForEach(topRows.indices, id: \.self) { index in
                    let row = topRows[index]
                    VStack(alignment: .leading, spacing: 3) {
                        HStack {
                            Text(row.0)
                                .font(.system(size: 9, design: .monospaced))
                                .foregroundStyle(Theme.textSecondary)
                                .lineLimit(1)
                            Spacer()
                            Text("\(row.1)")
                                .font(.system(size: 9, design: .monospaced))
                                .foregroundStyle(Theme.textMuted)
                        }
                        UsageBar(
                            percent: Double(row.1) / Double(maxValue) * 100,
                            color: Theme.red.opacity(0.55),
                            height: 3
                        )
                    }
                }
            }
        }
    }
}

// MARK: - Export / share

struct ExportFile: Identifiable {
    let id = UUID()
    let url: URL
}

struct ShareSheet: UIViewControllerRepresentable {
    let items: [Any]

    func makeUIViewController(context: Context) -> UIActivityViewController {
        UIActivityViewController(activityItems: items, applicationActivities: nil)
    }

    func updateUIViewController(_ controller: UIActivityViewController, context: Context) {}
}
