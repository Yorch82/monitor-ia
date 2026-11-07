import SwiftUI

// ============================================================================
// Gauges circulares y tarjetas compactas de hardware.
// ============================================================================

struct RingGauge: View {
    let value: Double?
    var label: String
    var centerText: String? = nil
    var size: CGFloat = 104
    var warn: Double = 70
    var crit: Double = 90
    var accent: Color = Theme.accent

    private var fraction: CGFloat {
        guard let value else { return 0 }
        return CGFloat(max(0, min(100, value)) / 100.0)
    }

    private var color: Color {
        guard let value else { return Theme.textMuted }
        if value >= crit { return Theme.red }
        if value >= warn { return Theme.amber }
        return accent == Theme.accent ? Theme.green : accent
    }

    private var display: String {
        if let centerText { return centerText }
        return value == nil ? "—" : Fmt.percent(value, maxDigits: 0)
    }

    var body: some View {
        ZStack {
            Circle()
                .stroke(Color.white.opacity(0.06), style: StrokeStyle(lineWidth: 9))
            Circle()
                .trim(from: 0, to: fraction)
                .stroke(color, style: StrokeStyle(lineWidth: 9, lineCap: .round))
                .rotationEffect(.degrees(-90))
                .shadow(color: color.opacity(0.35), radius: 5, x: 0, y: 0)
                .animation(.easeInOut(duration: 0.45), value: fraction)
            VStack(spacing: 1) {
                Text(display)
                    .font(.system(size: size * 0.19, weight: .semibold, design: .rounded))
                    .monospacedDigit()
                    .foregroundStyle(Theme.textPrimary)
                    .lineLimit(1)
                    .minimumScaleFactor(0.6)
                Text(label.uppercased())
                    .font(.system(size: size * 0.065, weight: .semibold))
                    .tracking(0.6)
                    .foregroundStyle(Theme.textMuted)
            }
            .padding(10)
        }
        .frame(width: size, height: size)
    }
}

struct CompactGaugeCard<Details: View>: View {
    let title: String
    let systemImage: String
    let gaugeValue: Double?
    let gaugeLabel: String
    let gaugeCenter: String?
    let accent: Color
    let details: Details

    init(
        title: String,
        systemImage: String,
        gaugeValue: Double?,
        gaugeLabel: String,
        gaugeCenter: String? = nil,
        accent: Color = Theme.accent,
        @ViewBuilder details: () -> Details
    ) {
        self.title = title
        self.systemImage = systemImage
        self.gaugeValue = gaugeValue
        self.gaugeLabel = gaugeLabel
        self.gaugeCenter = gaugeCenter
        self.accent = accent
        self.details = details()
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 6) {
                Image(systemName: systemImage)
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(accent)
                Text(title.uppercased())
                    .font(.system(size: 8, weight: .bold))
                    .tracking(0.8)
                    .foregroundStyle(Theme.textMuted)
                Spacer()
            }
            HStack(spacing: 8) {
                RingGauge(
                    value: gaugeValue,
                    label: gaugeLabel,
                    centerText: gaugeCenter,
                    size: 88,
                    accent: accent
                )
                VStack(alignment: .leading, spacing: 5) {
                    details
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
        .padding(12)
        .frame(maxWidth: .infinity, minHeight: 140, alignment: .topLeading)
        .cardStyle()
    }
}
