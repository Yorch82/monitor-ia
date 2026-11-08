import SwiftUI

// ============================================================================
// Pestaña Refrigeración (iOS): temperaturas, perfiles y control de ventiladores.
// ============================================================================

struct CoolingView: View {
    @EnvironmentObject private var store: MonitorStore
    @State private var notice: String?
    @State private var noticeIsError = false

    var body: some View {
        ZStack {
            AppBackground()
            ScrollView {
                VStack(spacing: 14) {
                    ScreenHeader(
                        title: "Refrigeración",
                        subtitle: "Temperaturas, RPM y perfiles",
                        systemImage: "wind",
                        accent: Theme.accent
                    ) {
                        HStack(spacing: 8) {
                            if let cooling = store.cooling {
                                controlChip(cooling)
                            }
                            Button {
                                Task { await store.loadCooling() }
                            } label: {
                                Image(systemName: "arrow.clockwise")
                                    .font(.system(size: 11, weight: .semibold))
                                    .foregroundStyle(Theme.textSecondary)
                                    .frame(width: 28, height: 28)
                                    .background(Circle().fill(Color.white.opacity(0.04)))
                                    .overlay(Circle().stroke(Theme.border, lineWidth: 1))
                            }
                            .disabled(store.isCoolingLoading)
                        }
                    }

                    if let notice {
                        banner(notice, isError: noticeIsError)
                    }

                    if let cooling = store.cooling {
                        if cooling.control.emergencyActive {
                            warningBanner(
                                "Protección térmica activa: ventiladores al 100 % hasta bajar de \(Fmt.number(cooling.control.emergencyReleaseC, maxDigits: 0)) ºC.",
                                color: Theme.red
                            )
                        }
                        if !cooling.control.enabled {
                            warningBanner(
                                "Solo lectura. Activa COOLING_CONTROL_ENABLED=true y monta /sys con docker-compose.cooling.yml para controlar los ventiladores.",
                                color: Theme.amber
                            )
                        } else if cooling.control.released {
                            warningBanner(
                                "Control devuelto a la BIOS/EC. Elige un perfil para volver a gestionar los ventiladores.",
                                color: Theme.accent
                            )
                        }
                        if let error = cooling.control.lastError {
                            warningBanner(error, color: Theme.red)
                        }

                        kpis(cooling)
                        profilesPanel(cooling)
                        temperaturesPanel(cooling)
                        controlPanel(cooling)
                        fansPanel(cooling)

                        Text("Control PWM vía /sys/class/hwmon y NVML (opcional). Mínimo \(Fmt.number(cooling.control.minPwmPct, maxDigits: 0)) % · emergencia \(Fmt.number(cooling.control.emergencyTempC, maxDigits: 0)) ºC. El perfil se guarda en el servidor y se aplica al arrancar.")
                            .font(.system(size: 9))
                            .foregroundStyle(Theme.textMuted)
                            .padding(.horizontal, 4)
                    } else if let error = store.coolingError {
                        Panel(title: "Sin datos", systemImage: "wifi.exclamationmark") {
                            Text(error)
                                .font(.system(size: 11))
                                .foregroundStyle(Theme.textSecondary)
                                .fixedSize(horizontal: false, vertical: true)
                            Button("Reintentar") {
                                Task { await store.loadCooling() }
                            }
                            .buttonStyle(GhostButtonStyle())
                        }
                    } else {
                        Panel(title: "Cargando refrigeración", systemImage: "wind") {
                            HStack(spacing: 10) {
                                ProgressView().tint(Theme.accent)
                                Text("Consultando sensores del servidor…")
                                    .font(.system(size: 11))
                                    .foregroundStyle(Theme.textSecondary)
                                Spacer()
                            }
                        }
                    }
                }
                .padding(.horizontal, 16)
                .padding(.top, 8)
                .padding(.bottom, 30)
            }
            .scrollIndicators(.hidden)
            .refreshable { await store.loadCooling() }
        }
        .task {
            await store.loadCooling()
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: 2_000_000_000)
                guard !Task.isCancelled else { return }
                await store.loadCooling()
            }
        }
    }

    // MARK: - KPIs

    private func kpis(_ cooling: CoolingSnapshot) -> some View {
        LazyVGrid(
            columns: [
                GridItem(.flexible(), spacing: 12),
                GridItem(.flexible(), spacing: 12),
            ],
            spacing: 12
        ) {
            KpiCard(
                title: "CPU",
                value: cooling.summary.cpuTempC.map { "\(Fmt.number($0, maxDigits: 1)) ºC" } ?? "—",
                subtitle: "\(cooling.temperatures.filter { $0.source == "cpu" }.count) sensores",
                systemImage: "thermometer.medium",
                accent: tempAccent(cooling.summary.cpuTempC, warn: 75, crit: 85),
                progress: cooling.summary.cpuTempC,
                footer: "verde <75 · ámbar 75-85 · rojo >85"
            )
            KpiCard(
                title: "GPU",
                value: cooling.summary.gpuTempC.map { "\(Fmt.number($0, maxDigits: 1)) ºC" } ?? "—",
                subtitle: "\(cooling.temperatures.filter { $0.source == "gpu" }.count) sensores",
                systemImage: "thermometer.medium",
                accent: tempAccent(cooling.summary.gpuTempC, warn: 75, crit: 83),
                progress: cooling.summary.gpuTempC,
                footer: "emergencia \(Fmt.number(cooling.control.emergencyTempC, maxDigits: 0)) ºC"
            )
            KpiCard(
                title: "Máximo",
                value: cooling.summary.maxTempC.map { "\(Fmt.number($0, maxDigits: 1)) ºC" } ?? "—",
                subtitle: "CPU/GPU más caliente",
                systemImage: "flame.fill",
                accent: cooling.control.emergencyActive ? Theme.red : Theme.accent,
                progress: cooling.summary.maxTempC,
                footer: cooling.control.emergencyActive ? "ventiladores al 100 %" : "protección térmica"
            )
            KpiCard(
                title: "Ventiladores",
                value: cooling.summary.avgFanRpm.map { "\(Fmt.number($0, maxDigits: 0)) RPM" } ?? "—",
                subtitle: "\(cooling.summary.fanCount) fans · \(cooling.summary.controllableFans) controlables",
                systemImage: "fanblades",
                accent: Theme.amber,
                footer: "actualizado \(Fmt.relative(cooling.updatedDate))"
            )
        }
    }

    // MARK: - Perfiles

    private func profilesPanel(_ cooling: CoolingSnapshot) -> some View {
        Panel(title: "Perfiles de refrigeración", systemImage: "snowflake") {
            LazyVGrid(
                columns: [
                    GridItem(.flexible(), spacing: 10),
                    GridItem(.flexible(), spacing: 10),
                ],
                spacing: 10
            ) {
                ForEach(cooling.profiles) { profile in
                    profileCard(profile, cooling: cooling)
                }
            }
            Text("Silencioso en invierno para reducir ruido; máximo en verano para contrarrestar el calor.")
                .font(.system(size: 9))
                .foregroundStyle(Theme.textMuted)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    private func profileCard(_ profile: CoolingProfileInfo, cooling: CoolingSnapshot) -> some View {
        let active = !cooling.control.released && cooling.control.profile == profile.id
        let enabled = cooling.control.enabled && cooling.control.writable && !store.isCoolingUpdating
        return Button {
            Task {
                let ok = await store.applyCoolingProfile(profile.id)
                setNotice(ok ? "Perfil \(profile.label) aplicado." : (store.coolingError ?? "No se pudo aplicar"), isError: !ok)
            }
        } label: {
            VStack(alignment: .leading, spacing: 6) {
                HStack {
                    Image(systemName: profileIcon(profile.id))
                        .font(.system(size: 15, weight: .semibold))
                        .foregroundStyle(active ? Theme.accent : Theme.textSecondary)
                    Spacer()
                    if active {
                        Text("ACTIVO")
                            .font(.system(size: 7, weight: .bold))
                            .tracking(0.5)
                            .foregroundStyle(Theme.accent)
                    }
                }
                Text(profile.label)
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(Theme.textPrimary)
                Text(profile.description)
                    .font(.system(size: 9))
                    .foregroundStyle(Theme.textMuted)
                    .lineLimit(2)
                Text(profile.targetPwmPct.map { "\(Fmt.number($0, maxDigits: 0))% PWM" } ?? "curva 25–100%")
                    .font(.system(size: 9, design: .monospaced))
                    .foregroundStyle(Theme.textMuted)
            }
            .frame(maxWidth: .infinity, minHeight: 100, alignment: .topLeading)
            .padding(12)
            .background(
                RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .fill(active ? Theme.accent.opacity(0.08) : Color.white.opacity(0.02))
            )
            .overlay(
                RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .stroke(active ? Theme.accent.opacity(0.5) : Theme.border, lineWidth: 1)
            )
        }
        .buttonStyle(.plain)
        .disabled(!enabled)
        .opacity(enabled || active ? 1 : 0.55)
    }

    // MARK: - Temperaturas

    private func temperaturesPanel(_ cooling: CoolingSnapshot) -> some View {
        let gauges = representativeTemperatures(cooling.temperatures)
        return Panel(title: "Temperaturas", systemImage: "thermometer") {
            if gauges.isEmpty {
                EmptyStateView(icon: "thermometer", title: "Sin sensores", message: "No se han encontrado sensores de temperatura.")
            } else {
                LazyVGrid(
                    columns: [
                        GridItem(.flexible(), spacing: 8),
                        GridItem(.flexible(), spacing: 8),
                    ],
                    spacing: 8
                ) {
                    ForEach(gauges) { temp in
                        VStack(spacing: 2) {
                            RingGauge(
                                value: temp.valueC,
                                label: sourceLabel(temp.source),
                                centerText: "\(Fmt.number(temp.valueC, maxDigits: 1)) ºC",
                                size: 96,
                                warn: temp.source == "gpu" ? 75 : 75,
                                crit: temp.source == "gpu" ? 83 : 85
                            )
                            Text(temp.label)
                                .font(.system(size: 8))
                                .foregroundStyle(Theme.textMuted)
                                .lineLimit(1)
                        }
                        .padding(6)
                        .background(
                            RoundedRectangle(cornerRadius: 12, style: .continuous)
                                .fill(Color.white.opacity(0.02))
                        )
                    }
                }
            }
            Divider().overlay(Theme.border)
            VStack(alignment: .leading, spacing: 5) {
                ForEach(cooling.temperatures) { temp in
                    HStack {
                        Text(sourceLabel(temp.source))
                            .font(.system(size: 8, weight: .bold))
                            .tracking(0.5)
                            .foregroundStyle(Theme.textMuted)
                            .frame(width: 52, alignment: .leading)
                        Text(temp.label)
                            .font(.system(size: 9))
                            .foregroundStyle(Theme.textSecondary)
                            .lineLimit(1)
                        Spacer()
                        Text("\(Fmt.number(temp.valueC, maxDigits: 1)) ºC")
                            .font(.system(size: 9, design: .monospaced))
                            .foregroundStyle(Theme.textPrimary)
                    }
                }
            }
        }
    }

    // MARK: - Control

    private func controlPanel(_ cooling: CoolingSnapshot) -> some View {
        let control = cooling.control
        let canControl = control.enabled && control.writable
        return Panel(title: "Control y seguridad", systemImage: "shield.lefthalf.filled") {
            VStack(spacing: 6) {
                StatRow(label: "PWM mínimo", value: "\(Fmt.number(control.minPwmPct, maxDigits: 0)) %")
                StatRow(label: "Emergencia", value: "≥ \(Fmt.number(control.emergencyTempC, maxDigits: 0)) ºC → 100 %")
                StatRow(label: "Liberar emergencia", value: "≤ \(Fmt.number(control.emergencyReleaseC, maxDigits: 0)) ºC")
                StatRow(label: "Restaurar al salir", value: control.restoreOnExit ? "Sí (BIOS)" : "No")
                StatRow(
                    label: "Estado",
                    value: control.emergencyActive
                        ? "Protección térmica"
                        : control.released
                            ? "Control BIOS"
                            : canControl
                                ? "Control activo"
                                : "Solo lectura",
                    highlight: control.emergencyActive
                )
            }
            HStack(spacing: 8) {
                Button {
                    Task {
                        let ok = await store.applyCoolingProfile("max")
                        setNotice(ok ? "Ventilación máxima aplicada." : (store.coolingError ?? "No se pudo aplicar"), isError: !ok)
                    }
                } label: {
                    Label("Máximo ahora", systemImage: "flame.fill")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(GhostButtonStyle())
                .disabled(!canControl || store.isCoolingUpdating)

                Button {
                    Task {
                        let ok = await store.releaseCoolingToBIOS()
                        setNotice(ok ? "Control devuelto a la BIOS." : (store.coolingError ?? "No se pudo liberar"), isError: !ok)
                    }
                } label: {
                    Label("BIOS", systemImage: "arrow.uturn.backward")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(GhostButtonStyle())
                .disabled(!canControl || store.isCoolingUpdating)
            }
            Text(control.note)
                .font(.system(size: 9))
                .foregroundStyle(Theme.textMuted)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    // MARK: - Ventiladores

    private func fansPanel(_ cooling: CoolingSnapshot) -> some View {
        Panel(title: "Ventiladores", systemImage: "fanblades") {
            if cooling.fans.isEmpty {
                EmptyStateView(
                    icon: "fanblades",
                    title: "Sin ventiladores",
                    message: "No se han encontrado canales de ventilador accesibles."
                )
            } else {
                VStack(spacing: 10) {
                    ForEach(cooling.fans) { fan in
                        FanControlRow(
                            fan: fan,
                            canControl: cooling.control.enabled && cooling.control.writable,
                            isUpdating: store.isCoolingUpdating,
                            onApply: { pwm in
                                Task {
                                    let ok = await store.applyFanPWM(fanID: fan.id, pwmPct: pwm)
                                    setNotice(ok ? "\(fan.label): \(Int(pwm)) % aplicado." : (store.coolingError ?? "No se pudo aplicar"), isError: !ok)
                                }
                            }
                        )
                    }
                }
            }
        }
    }

    // MARK: - Helpers

    private func setNotice(_ text: String, isError: Bool) {
        notice = text
        noticeIsError = isError
    }

    private func representativeTemperatures(_ temps: [CoolingTemperature]) -> [CoolingTemperature] {
        var result: [CoolingTemperature] = []
        for source in ["cpu", "gpu", "system", "storage"] {
            let candidates = temps.filter { $0.source == source }
            if let best = candidates.max(by: { $0.valueC < $1.valueC }) {
                result.append(best)
            }
        }
        return Array(result.prefix(4))
    }

    private func sourceLabel(_ source: String) -> String {
        switch source {
        case "cpu": return "CPU"
        case "gpu": return "GPU"
        case "storage": return "SSD"
        default: return "SIS"
        }
    }

    private func profileIcon(_ id: String) -> String {
        switch id {
        case "silent": return "snowflake"
        case "max": return "flame.fill"
        case "auto": return "thermometer.medium"
        default: return "wind"
        }
    }

    private func tempAccent(_ temp: Double?, warn: Double, crit: Double) -> Color {
        guard let temp else { return Theme.textMuted }
        if temp >= crit { return Theme.red }
        if temp >= warn { return Theme.amber }
        return Theme.green
    }

    private func controlChip(_ cooling: CoolingSnapshot) -> some View {
        let label: String
        let color: Color
        if cooling.control.emergencyActive {
            label = "EMERGENCIA"; color = Theme.red
        } else if cooling.control.released {
            label = "CONTROL BIOS"; color = Theme.accent
        } else if cooling.control.enabled && cooling.control.writable {
            label = "CONTROL ACTIVO"; color = Theme.green
        } else {
            label = "SOLO LECTURA"; color = Theme.amber
        }
        return Text(label)
            .font(.system(size: 7, weight: .bold))
            .tracking(0.5)
            .foregroundStyle(color)
            .padding(.horizontal, 7)
            .padding(.vertical, 4)
            .background(Capsule().fill(color.opacity(0.10)))
            .overlay(Capsule().stroke(color.opacity(0.3), lineWidth: 1))
    }

    private func warningBanner(_ text: String, color: Color) -> some View {
        HStack(alignment: .top, spacing: 8) {
            Image(systemName: "exclamationmark.triangle.fill")
                .font(.system(size: 11))
                .foregroundStyle(color)
            Text(text)
                .font(.system(size: 10))
                .foregroundStyle(color.opacity(0.95))
                .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 0)
        }
        .padding(10)
        .background(RoundedRectangle(cornerRadius: 12, style: .continuous).fill(color.opacity(0.10)))
        .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).stroke(color.opacity(0.3), lineWidth: 1))
    }

    private func banner(_ text: String, isError: Bool) -> some View {
        let color = isError ? Theme.red : Theme.green
        return HStack(spacing: 8) {
            Image(systemName: isError ? "exclamationmark.triangle.fill" : "checkmark.circle.fill")
                .font(.system(size: 11))
                .foregroundStyle(color)
            Text(text)
                .font(.system(size: 10))
                .foregroundStyle(Theme.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 0)
        }
        .padding(10)
        .background(RoundedRectangle(cornerRadius: 12, style: .continuous).fill(color.opacity(0.10)))
    }
}

// MARK: - Fila de ventilador

private struct FanControlRow: View {
    let fan: CoolingFan
    let canControl: Bool
    let isUpdating: Bool
    let onApply: (Double) -> Void

    @State private var value: Double

    init(fan: CoolingFan, canControl: Bool, isUpdating: Bool, onApply: @escaping (Double) -> Void) {
        self.fan = fan
        self.canControl = canControl
        self.isUpdating = isUpdating
        self.onApply = onApply
        _value = State(initialValue: fan.pwmPct ?? fan.minPwmPct)
    }

    private var enabled: Bool { canControl && fan.controllable }

    var body: some View {
        VStack(alignment: .leading, spacing: 7) {
            HStack {
                Image(systemName: fan.kind == "gpu" ? "cpu" : "fanblades")
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(fan.kind == "gpu" ? Theme.violet : Theme.accent)
                VStack(alignment: .leading, spacing: 1) {
                    Text(fan.label)
                        .font(.system(size: 11, weight: .medium))
                        .foregroundStyle(Theme.textPrimary)
                    Text("\(fan.kind == "gpu" ? "GPU" : "SISTEMA") · \(fan.isProtected == true ? "BOMBA PROTEGIDA" : fan.controllable ? "CONTROLABLE" : "SOLO LECTURA")")
                        .font(.system(size: 7))
                        .tracking(0.5)
                        .foregroundStyle(Theme.textMuted)
                }
                Spacer()
                Text(fan.rpm.map { "\(Fmt.integer($0)) RPM" } ?? "— RPM")
                    .font(.system(size: 10, weight: .semibold, design: .monospaced))
                    .foregroundStyle(Theme.textSecondary)
            }

            HStack {
                Text("PWM")
                    .font(.system(size: 8))
                    .foregroundStyle(Theme.textMuted)
                Spacer()
                Text(fan.pwmPct.map { "\(Fmt.number($0, maxDigits: 0)) % actual · \(Int(value)) %" } ?? "—")
                    .font(.system(size: 8, design: .monospaced))
                    .foregroundStyle(Theme.textSecondary)
            }
            Slider(value: $value, in: fan.minPwmPct...100, step: 1)
                .tint(Theme.accent)
                .disabled(!enabled || isUpdating)

            HStack {
                Text("\(Fmt.number(fan.minPwmPct, maxDigits: 0)) % mín.")
                Spacer()
                Text("100 %")
            }
            .font(.system(size: 7))
            .foregroundStyle(Theme.textMuted)

            if let error = fan.lastError {
                Text(error)
                    .font(.system(size: 8))
                    .foregroundStyle(Theme.red)
            }

            if enabled {
                Button {
                    onApply(value)
                } label: {
                    Text(isUpdating ? "Aplicando…" : "Aplicar ventilador")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(GhostButtonStyle())
                .disabled(isUpdating || Int(value) == Int(fan.pwmPct ?? -1))
            } else {
                Text(
                    fan.isProtected == true
                        ? "Bomba protegida: control gestionado por la BIOS"
                        : canControl ? "Sin canal PWM escribible" : "Activa el control para editar"
                )
                    .font(.system(size: 8))
                    .foregroundStyle(Theme.amber.opacity(0.8))
                    .frame(maxWidth: .infinity)
            }
        }
        .padding(12)
        .background(
            RoundedRectangle(cornerRadius: 13, style: .continuous)
                .fill(Color.white.opacity(0.02))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 13, style: .continuous)
                .stroke(Theme.border, lineWidth: 1)
        )
        .onChange(of: fan.pwmPct) { _, newValue in
            if let newValue { value = newValue }
        }
    }
}
