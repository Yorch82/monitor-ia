import SwiftUI

// ============================================================================
// Raíz de la app: TabView con Resumen, Seguridad y Ajustes.
// ============================================================================

struct RootView: View {
    @EnvironmentObject private var store: MonitorStore

    var body: some View {
        TabView {
            DashboardView()
                .tabItem {
                    Label("Resumen", systemImage: "waveform.path.ecg")
                }

            SecurityView()
                .tabItem {
                    Label("Seguridad", systemImage: "shield.lefthalf.filled")
                }

            SettingsView()
                .tabItem {
                    Label("Ajustes", systemImage: "gearshape.fill")
                }
        }
        .tint(Theme.accent)
        .toolbarBackground(Theme.background, for: .tabBar)
        .toolbarBackground(.visible, for: .tabBar)
    }
}
