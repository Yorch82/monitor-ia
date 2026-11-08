import Foundation
import SwiftUI

// ============================================================================
// Pestaña Ajustes: servidor, energía, inferencia, muestreo, umbrales y datos.
// ============================================================================

struct SettingsView: View {
    @EnvironmentObject private var store: MonitorStore

    @State private var draft = SettingsDraft()
    @State private var loaded = false
    @State private var hasStoredAPIKey = false
    @State private var serverField = ""
    @State private var banner: String?
    @State private var bannerIsError = false
    @State private var isUpdatingServer = false
    @State private var isExporting = false
    @State private var exportRange: ChartRange = .day
    @State private var exportFile: ExportFile?
    @State private var showResetSession = false
    @State private var showResetDefaults = false

    var body: some View {
        ZStack {
            AppBackground()
            ScrollView {
                VStack(spacing: 14) {
                    ScreenHeader(
                        title: "Ajustes",
                        subtitle: "Servidor, coste, inferencia y alertas",
                        systemImage: "gearshape.fill",
                        accent: Theme.accent
                    ) {
                        Button {
                            saveSettings()
                        } label: {
                            if store.isSavingSettings {
                                ProgressView()
                                    .tint(Color(hex: 0x05070D))
                                    .frame(width: 54)
                            } else {
                                Text("Guardar")
                            }
                        }
                        .buttonStyle(PrimaryButtonStyle())
                        .disabled(!loaded || store.isSavingSettings)
                    }

                    if let banner {
                        bannerView(banner, isError: bannerIsError)
                    }

                    // El editor de servidor debe estar siempre disponible, incluso si
                    // la URL actual no responde y no se pudieron cargar los ajustes.
                    serverPanel

                    if !loaded {
                        loadingPanel
                    } else {
                        energyPanel
                        inferencePanel
                        samplingPanel
                        thresholdsPanel
                        dataPanel
                        aboutPanel
                    }
                }
                .padding(.horizontal, 16)
                .padding(.top, 8)
                .padding(.bottom, 30)
            }
            .scrollIndicators(.hidden)
        }
        .task { await loadSettings() }
        .onChange(of: store.settings) { _, newValue in
            if let newValue, !loaded {
                apply(newValue)
            }
        }
        .sheet(item: $exportFile) { file in
            ShareSheet(items: [file.url])
                .presentationDetents([.medium, .large])
        }
        .alert("¿Reiniciar la sesión?", isPresented: $showResetSession) {
            Button("Reiniciar", role: .destructive) {
                Task {
                    let ok = await store.resetSession()
                    banner = ok ? "Sesión reiniciada: tokens, energía y coste a cero." : (store.lastError ?? "No se pudo reiniciar")
                    bannerIsError = !ok
                }
            }
            Button("Cancelar", role: .cancel) {}
        } message: {
            Text("Se borran los contadores de tokens, energía y coste de la sesión actual. El histórico no se toca.")
        }
        .confirmationDialog(
            "Restaurar los valores del .env",
            isPresented: $showResetDefaults,
            titleVisibility: .visible
        ) {
            Button("Restaurar defaults", role: .destructive) {
                Task { await restoreDefaults() }
            }
            Button("Cancelar", role: .cancel) {}
        } message: {
            Text("Se descartan los ajustes guardados en el servidor y se vuelve a los valores del archivo .env.")
        }
    }

    // MARK: - Carga / guardado

    private func loadSettings() async {
        serverField = store.serverURL
        if store.settings == nil {
            await store.loadSettings()
        }
        serverField = store.serverURL
        if let settings = store.settings {
            apply(settings)
        }
    }

    private func apply(_ settings: PublicSettings) {
        draft = SettingsDraft(settings: settings)
        hasStoredAPIKey = settings.inferenceApiKeySet
        loaded = true
    }

    private func saveSettings() {
        Task {
            let ok = await store.saveSettings(draft.update())
            banner = ok ? "Ajustes guardados y aplicados en caliente." : (store.settingsError ?? "No se pudieron guardar los ajustes")
            bannerIsError = !ok
            if ok {
                draft.apiKey = ""
                draft.clearApiKey = false
                if let settings = store.settings {
                    hasStoredAPIKey = settings.inferenceApiKeySet
                }
            }
        }
    }

    private func updateServer() {
        Task {
            isUpdatingServer = true
            loaded = false
            let ok = await store.updateServerURL(serverField)
            isUpdatingServer = false
            guard ok else {
                banner = store.lastError ?? "URL de servidor inválida"
                bannerIsError = true
                loaded = true
                return
            }
            serverField = store.serverURL
            await store.loadSettings()
            if let settings = store.settings {
                apply(settings)
                banner = "Servidor actualizado: \(store.serverURL)"
                bannerIsError = false
            } else {
                loaded = true
                banner = store.settingsError ?? "Conectado, pero no se pudieron cargar los ajustes del backend."
                bannerIsError = true
            }
        }
    }

    private func restoreDefaults() async {
        let ok = await store.restoreDefaultSettings()
        if ok, let settings = store.settings {
            apply(settings)
            banner = "Ajustes restaurados a los valores del .env."
            bannerIsError = false
        } else {
            banner = store.settingsError ?? "No se pudieron restaurar los ajustes"
            bannerIsError = true
        }
    }

    private func exportCSV() {
        Task {
            isExporting = true
            do {
                let url = try await store.downloadCSV(range: exportRange)
                exportFile = ExportFile(url: url)
                banner = "CSV descargado. Compártelo o guárdalo en Archivos."
                bannerIsError = false
            } catch {
                banner = "No se pudo exportar el CSV: \(error.localizedDescription)"
                bannerIsError = true
            }
            isExporting = false
        }
    }

    // MARK: - Servidor (app)

    private var serverPanel: some View {
        Panel(title: "Servidor de Monitor IA", systemImage: "server.rack") {
            FieldBox(
                label: "URL del dashboard/backend",
                help: "Por Tailscale usa http://100.115.55.87:8080 (o http://claudio.tailf02b11.ts.net:8080). No uses https://claudio.tailf02b11.ts.net: ese 443 sirve Open WebUI, no Monitor IA."
            ) {
                TextField("http://100.115.55.87:8080", text: $serverField)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .keyboardType(.URL)
                    .textContentType(.URL)
                    .font(.system(size: 12, design: .monospaced))
                    .darkField()
            }

            HStack(spacing: 6) {
                quickServerButton("LAN", value: "http://192.168.1.35:8080")
                quickServerButton("Tailscale", value: "http://100.115.55.87:8080")
                Spacer()
                Button {
                    updateServer()
                } label: {
                    if isUpdatingServer {
                        ProgressView().tint(Theme.textPrimary)
                    } else {
                        Text("Aplicar")
                    }
                }
                .buttonStyle(GhostButtonStyle())
                .disabled(isUpdatingServer || serverField.trimmingCharacters(in: .whitespaces).isEmpty)
            }

            HStack(spacing: 6) {
                ConnectionBadge(state: store.connection)
                Text(store.serverURL)
                    .font(.system(size: 9, design: .monospaced))
                    .foregroundStyle(Theme.textMuted)
                    .lineLimit(1)
                Spacer()
            }

            Text("Proxy IA OpenAI-compatible: \(store.serverURL)/proxy/v1")
                .font(.system(size: 9, design: .monospaced))
                .foregroundStyle(Theme.textMuted)
                .textSelection(.enabled)
        }
    }

    private func quickServerButton(_ title: String, value: String) -> some View {
        Button {
            serverField = value
        } label: {
            Text(title)
        }
        .buttonStyle(GhostButtonStyle())
    }

    // MARK: - Energía

    private var energyPanel: some View {
        Panel(title: "Energía y coste", systemImage: "eurosign.circle.fill") {
            FieldBox(label: "Precio del kWh (€/kWh)", help: "Precio de tu tarifa eléctrica, impuestos incluidos.") {
                TextField("0,15", value: $draft.pricePerKwh, format: .number.precision(.fractionLength(0...3)))
                    .keyboardType(.decimalPad)
                    .darkField()
            }
            FieldBox(label: "Límite de coste diario (€)", help: "Alerta cuando el coste acumulado del día lo supere.") {
                TextField("1,00", value: $draft.dailyCostEur, format: .number.precision(.fractionLength(0...2)))
                    .keyboardType(.decimalPad)
                    .darkField()
            }
        }
    }

    // MARK: - Inferencia

    private var inferencePanel: some View {
        Panel(title: "Servidor de inferencia", systemImage: "brain.head.profile") {
            ToggleRow(
                title: "Modo simulación",
                help: "Datos sintéticos sin GPU ni modelo. Desactívalo en el servidor real.",
                isOn: $draft.simulationMode
            )

            FieldBox(label: "URL base OpenAI-compatible", help: "Ollama http://host:11434/v1 · llama.cpp http://host:8080/v1 · vLLM http://host:8000/v1") {
                TextField("http://host:11434/v1", text: $draft.inferenceBaseUrl)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .keyboardType(.URL)
                    .font(.system(size: 11))
                    .darkField()
            }

            FieldBox(label: "URL de métricas Prometheus (opcional)", help: "Vacío → se deduce {base−/v1}/metrics. Solo vLLM/llama.cpp.") {
                TextField("https://…/metrics", text: $draft.inferenceMetricsUrl)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .keyboardType(.URL)
                    .font(.system(size: 11))
                    .darkField()
            }

            FieldBox(label: "Modelo (display)") {
                TextField("local-model", text: $draft.inferenceModel)
                    .autocorrectionDisabled()
                    .font(.system(size: 12))
                    .darkField()
            }

            HStack(spacing: 10) {
                FieldBox(label: "Ventana de contexto (tokens)") {
                    TextField("8192", value: $draft.contextWindow, format: .number)
                        .keyboardType(.numberPad)
                        .font(.system(size: 12, design: .monospaced))
                        .darkField()
                }
                FieldBox(label: "Retención histórica (h)") {
                    TextField("24", value: $draft.historyRetentionHours, format: .number)
                        .keyboardType(.numberPad)
                        .font(.system(size: 12, design: .monospaced))
                        .darkField()
                }
            }

            menuField(title: "Fuente de tokens", selection: $draft.tokenSource, options: [
                ("auto", "auto"),
                ("proxy", "proxy (recomendado)"),
                ("prometheus", "prometheus"),
                ("none", "none"),
            ])

            menuField(title: "Proveedor de GPU", selection: $draft.gpuProvider, options: [
                ("auto", "auto"),
                ("nvidia", "nvidia"),
                ("amd", "amd"),
                ("apple", "apple"),
                ("none", "none"),
            ])

            FieldBox(
                label: hasStoredAPIKey ? "API key guardada · escribe otra para cambiarla" : "API key (opcional)",
                help: "Se almacena en el servidor; la app nunca recibe la clave guardada."
            ) {
                SecureField(hasStoredAPIKey ? "••••••••" : "sk-…", text: $draft.apiKey)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .darkField()
                if hasStoredAPIKey {
                    Toggle("Borrar la clave guardada", isOn: $draft.clearApiKey)
                        .font(.system(size: 10))
                        .tint(Theme.red)
                }
            }

            FieldBox(label: "Webhook de alertas (opcional)", help: "POST JSON cada vez que una alerta se activa o escala.") {
                TextField("https://hooks…", text: $draft.webhookUrl)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .keyboardType(.URL)
                    .font(.system(size: 11))
                    .darkField()
            }

            HStack {
                Text("Fuente")
                    .font(.system(size: 10))
                    .foregroundStyle(Theme.textMuted)
                Spacer()
                Text(store.snapshot?.tokens.source.uppercased() ?? "—")
                    .font(.system(size: 10, weight: .semibold, design: .monospaced))
                    .foregroundStyle(Theme.accent)
            }
        }
    }

    // MARK: - Muestreo

    private var samplingPanel: some View {
        Panel(title: "Muestreo", systemImage: "timer") {
            FieldBox(label: "Intervalo de refresco (ms)", help: "Cada cuánto se muestrean y emiten métricas (250–60000 ms).") {
                TextField("1000", value: $draft.refreshIntervalMs, format: .number)
                    .keyboardType(.numberPad)
                    .font(.system(size: 12, design: .monospaced))
                    .darkField()
            }
        }
    }

    // MARK: - Umbrales

    private var thresholdsPanel: some View {
        Panel(title: "Umbrales de alerta", systemImage: "exclamationmark.triangle") {
            HStack(spacing: 10) {
                thresholdField("Contexto %", value: $draft.contextPct)
                thresholdField("GPU temp ºC", value: $draft.gpuTempC)
            }
            HStack(spacing: 10) {
                thresholdField("VRAM %", value: $draft.vramPct)
                thresholdField("RAM %", value: $draft.ramPct)
            }
        }
    }

    private func thresholdField(_ label: String, value: Binding<Double>) -> some View {
        FieldBox(label: label) {
            TextField("", value: value, format: .number.precision(.fractionLength(0...1)))
                .keyboardType(.decimalPad)
                .font(.system(size: 12, design: .monospaced))
                .darkField()
        }
    }

    // MARK: - Datos

    private var dataPanel: some View {
        Panel(title: "Datos", systemImage: "externaldrive") {
            HStack(spacing: 8) {
                Menu {
                    ForEach(ChartRange.allCases) { range in
                        Button {
                            exportRange = range
                        } label: {
                            if exportRange == range {
                                Label(range.shortLabel, systemImage: "checkmark")
                            } else {
                                Text(range.shortLabel)
                            }
                        }
                    }
                } label: {
                    HStack(spacing: 4) {
                        Text("CSV \(exportRange.shortLabel)")
                        Image(systemName: "chevron.down")
                            .font(.system(size: 8, weight: .bold))
                    }
                    .font(.system(size: 11, weight: .medium))
                    .foregroundStyle(Theme.textSecondary)
                    .padding(.horizontal, 10)
                    .padding(.vertical, 8)
                    .background(Capsule().fill(Color.white.opacity(0.04)))
                    .overlay(Capsule().stroke(Theme.border, lineWidth: 1))
                }

                Button {
                    exportCSV()
                } label: {
                    if isExporting {
                        ProgressView().tint(Theme.textPrimary)
                    } else {
                        Label("Exportar histórico", systemImage: "square.and.arrow.up")
                    }
                }
                .buttonStyle(GhostButtonStyle())
                .disabled(isExporting)
                Spacer()
            }

            Button {
                showResetSession = true
            } label: {
                Label("Reiniciar sesión (tokens, energía y coste)", systemImage: "arrow.counterclockwise")
            }
            .buttonStyle(GhostButtonStyle())

            Button {
                showResetDefaults = true
            } label: {
                Label("Restaurar ajustes del .env", systemImage: "arrow.uturn.backward")
                    .foregroundStyle(Theme.red)
            }
            .buttonStyle(GhostButtonStyle())

            Text("El histórico SQLite no se borra al reiniciar la sesión. Los ajustes guardados aquí viven en el servidor.")
                .font(.system(size: 9))
                .foregroundStyle(Theme.textMuted)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    private var aboutPanel: some View {
        Panel(title: "Acerca de", systemImage: "info.circle") {
            HStack {
                Text("Monitor IA · iOS")
                    .font(.system(size: 11, weight: .medium))
                    .foregroundStyle(Theme.textSecondary)
                Spacer()
                Text("v1.0.0")
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundStyle(Theme.textMuted)
            }
            Text("Cliente nativo para iPhone 16 Pro del backend de observabilidad de IA. Requiere Monitor IA v1.0 en el servidor y acceso a la LAN o VPN.")
                .font(.system(size: 9))
                .foregroundStyle(Theme.textMuted)
                .fixedSize(horizontal: false, vertical: true)
            Text("Sin autenticación propia: mantén el servidor restringido a tu red/VPN.")
                .font(.system(size: 9))
                .foregroundStyle(Theme.amber.opacity(0.8))
        }
    }

    // MARK: - Estado UI

    private var loadingPanel: some View {
        Panel(title: "Cargando ajustes", systemImage: "gearshape") {
            HStack(spacing: 10) {
                ProgressView().tint(Theme.accent)
                Text(store.settingsError ?? "Conectando con el servidor…")
                    .font(.system(size: 11))
                    .foregroundStyle(Theme.textSecondary)
                    .lineLimit(2)
                Spacer()
                Button("Reintentar") {
                    Task {
                        await store.loadSettings()
                        if let settings = store.settings { apply(settings) }
                    }
                }
                .buttonStyle(GhostButtonStyle())
            }
        }
    }

    private func bannerView(_ text: String, isError: Bool) -> some View {
        HStack(spacing: 8) {
            Image(systemName: isError ? "exclamationmark.triangle.fill" : "checkmark.circle.fill")
                .font(.system(size: 12))
                .foregroundStyle(isError ? Theme.red : Theme.green)
            Text(text)
                .font(.system(size: 10))
                .foregroundStyle(Theme.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 0)
        }
        .padding(10)
        .background(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .fill((isError ? Theme.red : Theme.green).opacity(0.10))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .stroke((isError ? Theme.red : Theme.green).opacity(0.30), lineWidth: 1)
        )
    }

    private func menuField(
        title: String,
        selection: Binding<String>,
        options: [(String, String)]
    ) -> some View {
        HStack {
            Text(title)
                .font(.system(size: 10))
                .foregroundStyle(Theme.textMuted)
            Spacer()
            Picker(selection: selection) {
                ForEach(options.indices, id: \.self) { index in
                    Text(options[index].1).tag(options[index].0)
                }
            } label: {
                Text(title)
            }
            .labelsHidden()
            .pickerStyle(.menu)
            .tint(Theme.accent)
        }
    }
}

// MARK: - Subcomponentes de formulario

private struct FieldBox<Content: View>: View {
    let label: String
    let help: String?
    let content: Content

    init(label: String, help: String? = nil, @ViewBuilder content: () -> Content) {
        self.label = label
        self.help = help
        self.content = content()
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 5) {
            Text(label)
                .font(.system(size: 10, weight: .medium))
                .foregroundStyle(Theme.textSecondary)
            content
            if let help {
                Text(help)
                    .font(.system(size: 8))
                    .foregroundStyle(Theme.textMuted)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }
}

private struct ToggleRow: View {
    let title: String
    let help: String
    @Binding var isOn: Bool

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            VStack(alignment: .leading, spacing: 3) {
                Text(title)
                    .font(.system(size: 11, weight: .medium))
                    .foregroundStyle(Theme.textPrimary)
                Text(help)
                    .font(.system(size: 8))
                    .foregroundStyle(Theme.textMuted)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Spacer()
            Toggle("", isOn: $isOn)
                .labelsHidden()
                .tint(Theme.accent)
        }
    }
}
