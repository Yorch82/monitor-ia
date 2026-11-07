import SwiftUI

// ============================================================================
// Tema visual dark "panel de control" compartido por toda la app iOS.
// ============================================================================

enum Theme {
    static let background = Color(hex: 0x05070D)
    static let backgroundSecondary = Color(hex: 0x0A0E18)
    static let card = Color(hex: 0x0D1220)
    static let cardElevated = Color(hex: 0x111827)
    static let border = Color.white.opacity(0.07)

    static let textPrimary = Color(hex: 0xE2E8F0)
    static let textSecondary = Color(hex: 0x94A3B8)
    static let textMuted = Color(hex: 0x64748B)

    static let accent = Color(hex: 0x22D3EE)
    static let blue = Color(hex: 0x38BDF8)
    static let deepBlue = Color(hex: 0x3B82F6)
    static let green = Color(hex: 0x34D399)
    static let amber = Color(hex: 0xFBBF24)
    static let red = Color(hex: 0xF87171)
    static let violet = Color(hex: 0xA78BFA)
    static let orange = Color(hex: 0xFB923C)
    static let pink = Color(hex: 0xF472B6)
    static let yellow = Color(hex: 0xFACC15)

    static let cardRadius: CGFloat = 20
}

extension Color {
    init(hex: UInt32, opacity: Double = 1.0) {
        let red = Double((hex >> 16) & 0xFF) / 255.0
        let green = Double((hex >> 8) & 0xFF) / 255.0
        let blue = Double(hex & 0xFF) / 255.0
        self.init(.sRGB, red: red, green: green, blue: blue, opacity: opacity)
    }
}

struct AppBackground: View {
    var body: some View {
        ZStack {
            Theme.background
            LinearGradient(
                colors: [
                    Theme.accent.opacity(0.07),
                    Color.clear,
                    Theme.deepBlue.opacity(0.05),
                ],
                startPoint: .topTrailing,
                endPoint: .bottomLeading
            )
        }
        .ignoresSafeArea()
    }
}

// MARK: - Modificadores reutilizables

private struct CardStyleModifier: ViewModifier {
    var accent: Color?

    func body(content: Content) -> some View {
        content
            .background(
                RoundedRectangle(cornerRadius: Theme.cardRadius, style: .continuous)
                    .fill(Theme.card)
            )
            .overlay(
                RoundedRectangle(cornerRadius: Theme.cardRadius, style: .continuous)
                    .stroke(Theme.border, lineWidth: 1)
            )
            .overlay(alignment: .top) {
                if let accent {
                    LinearGradient(
                        colors: [accent.opacity(0.85), accent.opacity(0.0)],
                        startPoint: .leading,
                        endPoint: .trailing
                    )
                    .frame(height: 2)
                    .clipShape(Capsule())
                }
            }
            .clipShape(RoundedRectangle(cornerRadius: Theme.cardRadius, style: .continuous))
    }
}

extension View {
    func cardStyle(accent: Color? = nil) -> some View {
        modifier(CardStyleModifier(accent: accent))
    }

    func darkField() -> some View {
        self
            .padding(.horizontal, 12)
            .padding(.vertical, 10)
            .background(
                RoundedRectangle(cornerRadius: 11, style: .continuous)
                    .fill(Theme.backgroundSecondary)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 11, style: .continuous)
                    .stroke(Theme.border, lineWidth: 1)
            )
            .foregroundStyle(Theme.textPrimary)
    }
}

// MARK: - Estilos de botón

struct PrimaryButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 14, weight: .semibold))
            .foregroundStyle(Color(hex: 0x05070D))
            .padding(.horizontal, 14)
            .padding(.vertical, 10)
            .background(
                RoundedRectangle(cornerRadius: 11, style: .continuous)
                    .fill(Theme.accent.opacity(configuration.isPressed ? 0.75 : 1))
            )
    }
}

struct GhostButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 13, weight: .medium))
            .foregroundStyle(Theme.textPrimary)
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .background(
                RoundedRectangle(cornerRadius: 10, style: .continuous)
                    .fill(Color.white.opacity(configuration.isPressed ? 0.10 : 0.04))
            )
            .overlay(
                RoundedRectangle(cornerRadius: 10, style: .continuous)
                    .stroke(Theme.border, lineWidth: 1)
            )
    }
}
