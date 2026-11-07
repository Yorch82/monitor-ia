import Charts
import Foundation
import SwiftUI

// ============================================================================
// Pestaña Seguridad: SSH, firewall, escaneos web, bots vs humanos y GeoIP.
// ============================================================================

struct SecurityView: View {
    @EnvironmentObject private var store: MonitorStore

    var body: some View {
        ZStack {
            AppBackground()
            ScrollView {
                VStack(spacing: 14) {
                    ScreenHeader(
                        title: "Seguridad del servidor",
                        subtitle: "SSH · firewall · escaneos web · GeoIP",
                        systemImage: "shield.lefthalf.filled",
                        accent: Theme.red
                    ) {
                        HStack(spacing: 8) {
                            rangeMenu
                            refreshButton
                        }
                    }

                    if let security = store.security {
                        if security.enabled {
                            sourceChips(security)
                            securityKPIs(security)
                            timelinePanel(security)
                            botDonutPanel(security)
                            topIPsPanel(security)
                            countriesPanel(security)
                            threatsPanel(security)
                            recentEventsPanel(security)
                            if !security.sources.ssh.available
                                || !security.sources.firewall.available
                                || !security.sources.web.available {
                                sourcesHelpPanel(security)
                            }
                            Text("Clasificación heurística bot/humano. Geolocalización opcional vía ip-api.com con caché local; las IPs privadas/CGNAT se muestran como Red local.")
                                .font(.system(size: 9))
                                .foregroundStyle(Theme.textMuted)
                                .padding(.horizontal, 4)
                        } else {
                            disabledPanel
                        }
                    } else if let error = store.securityError {
                        offlinePanel(error)
                    } else {
                        loadingPanel
                    }
                }
                .padding(.horizontal, 16)
                .padding(.top, 8)
                .padding(.bottom, 30)
            }
            .scrollIndicators(.hidden)
            .refreshable { await store.loadSecurity() }
        }
        .task {
            await store.loadSecurity()
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: 10_000_000_000)
                guard !Task.isCancelled else { return }
                await store.loadSecurity()
            }
        }
    }

    // MARK: - Cabecera

    private var rangeMenu: some View {
        Menu {
            ForEach(SecurityRange.allCases) { range in
                Button {
                    store.setSecurityRange(range)
                } label: {
                    if store.securityRange == range {
                        Label(range.label, systemImage: "checkmark")
                    } else {
                        Text(range.label)
                    }
                }
            }
        } label: {
            HStack(spacing: 4) {
                Text(store.securityRange.label)
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

    private var refreshButton: some View {
        Button {
            Task { await store.loadSecurity() }
        } label: {
            Image(systemName: "arrow.clockwise")
                .font(.system(size: 11, weight: .semibold))
                .foregroundStyle(Theme.textSecondary)
                .frame(width: 28, height: 28)
                .background(Circle().fill(Color.white.opacity(0.04)))
                .overlay(Circle().stroke(Theme.border, lineWidth: 1))
        }
        .disabled(store.isSecurityLoading)
        .opacity(store.isSecurityLoading ? 0.5 : 1)
    }

    // MARK: - Fuentes

    private func sourceChips(_ security: SecuritySnapshot) -> some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 6) {
                SourceChip(label: "SSH", isOn: security.sources.ssh.available == true)
                SourceChip(label: "Firewall", isOn: security.sources.firewall.available == true)
                SourceChip(label: "Web nginx", isOn: security.sources.web.available == true)
                SourceChip(
                    label: security.sources.geoip.enabled ? "GeoIP" : "GeoIP off",
                    isOn: security.sources.geoip.enabled,
                    isNeutral: !security.sources.geoip.enabled
                )
                Text("retención \(security.sources.retentionHours) h")
                    .font(.system(size: 8))
                    .foregroundStyle(Theme.textMuted)
                    .padding(.leading, 2)
            }
            .padding(.horizontal, 1)
        }
    }

    // MARK: - KPIs

    private func securityKPIs(_ security: SecuritySnapshot) -> some View {
        let summary = security.summary
        return LazyVGrid(
            columns: [
                GridItem(.flexible(), spacing: 12),
                GridItem(.flexible(), spacing: 12),
            ],
            spacing: 12
        ) {
            KpiCard(
                title: "SSH fallidos",
                value: Fmt.integer(summary.sshFailed),
                subtitle: "\(Fmt.integer(summary.sshScan)) escaneos SSH",
                systemImage: "terminal",
                accent: summary.sshFailed > 0 ? Theme.red : Theme.green,
                footer: summary.lastSshSuccess.map {
                    "último login \(Fmt.relative($0.date))"
                } ?? "sin logins correctos"
            )
            KpiCard(
                title: "IPs únicas",
                value: Fmt.integer(summary.uniqueIps),
                subtitle: "\(Fmt.number(summary.eventsPerHour, maxDigits: 2)) eventos/hora",
                systemImage: "globe",
                accent: Theme.accent,
                footer: "\(Fmt.integer(summary.totalEvents)) eventos en el rango"
            )
            KpiCard(
                title: "Países",
                value: Fmt.integer(summary.countries),
                subtitle: summary.topCountry.map {
                    "\(Fmt.flag($0.countryCode)) \($0.country)"
                } ?? "sin datos",
                systemImage: "mappin.and.ellipse",
                accent: Theme.deepBlue,
                footer: "origen de las IPs externas"
            )
            KpiCard(
                title: "Logins SSH",
                value: Fmt.integer(summary.sshSuccess),
                subtitle: summary.lastSshSuccess.map {
                    "\($0.username ?? "?") · \(Fmt.flag($0.countryCode)) \($0.country ?? "")"
                } ?? "sin accesos",
                systemImage: "checkmark.shield",
                accent: summary.sshSuccess > 0 ? Theme.amber : Theme.green,
                footer: "accesos completados correctamente"
            )
            KpiCard(
                title: "Web sospechosa",
                value: Fmt.integer(summary.webSuspicious),
                subtitle: security.topPaths.first.map {
                    String($0.path.prefix(28))
                } ?? "sin escaneos web",
                systemImage: "exclamationmark.triangle",
                accent: summary.webSuspicious > 0 ? Theme.violet : Theme.green,
                footer: "\(Fmt.integer(summary.firewallBlocks)) bloqueos de firewall"
            )
            KpiCard(
                title: "Bots",
                value: summary.botPct.map { Fmt.percent($0) } ?? "—",
                subtitle: "\(summary.bots) bots · \(summary.humans) humanos",
                systemImage: "person.crop.circle.badge.xmark",
                accent: (summary.botPct ?? 0) > 70 ? Theme.red : Theme.amber,
                progress: summary.botPct,
                footer: "clasificación por IP única"
            )
        }
    }

    // MARK: - Timeline

    private struct SeriesPoint: Identifiable {
        let id: String
        let date: Date
        let kind: String
        let count: Int
    }

    private func seriesPoints(_ security: SecuritySnapshot) -> [SeriesPoint] {
        var result: [SeriesPoint] = []
        for point in security.timeline {
            let values: [(String, Int)] = [
                ("SSH fallidos", point.sshFailed),
                ("Escaneos SSH", point.sshScan),
                ("Firewall", point.firewallBlocks),
                ("Web sospechosa", point.webSuspicious),
                ("Logins SSH", point.sshSuccess),
            ]
            for (label, count) in values where count > 0 {
                result.append(
                    SeriesPoint(
                        id: "\(point.t)-\(label)",
                        date: point.date,
                        kind: label,
                        count: count
                    )
                )
            }
        }
        return result
    }

    private func timelinePanel(_ security: SecuritySnapshot) -> some View {
        let series = seriesPoints(security)
        return Panel(title: "Actividad de seguridad", systemImage: "shield.lefthalf.filled") {
            if series.isEmpty {
                EmptyStateView(
                    icon: "shield.slash",
                    title: "Sin eventos",
                    message: "No se han registrado intentos en el rango seleccionado."
                )
                .frame(height: 190)
            } else {
                Chart(series) { point in
                    BarMark(
                        x: .value("Hora", point.date),
                        y: .value("Eventos", point.count)
                    )
                    .foregroundStyle(by: .value("Tipo", point.kind))
                    .cornerRadius(2)
                }
                .chartForegroundStyleScale([
                    "SSH fallidos": Theme.red,
                    "Escaneos SSH": Theme.amber,
                    "Firewall": Theme.orange,
                    "Web sospechosa": Theme.violet,
                    "Logins SSH": Theme.green,
                ])
                .chartLegend(.hidden)
                .frame(height: 210)
                .chartXScale(domain: securityXDomain(security))
                .chartXAxis {
                    AxisMarks(values: .automatic(desiredCount: 4)) { value in
                        AxisGridLine(stroke: StrokeStyle(lineWidth: 0.5))
                            .foregroundStyle(Theme.border)
                        AxisValueLabel {
                            if let date = value.as(Date.self) {
                                Text(Fmt.securityTime(date, range: store.securityRange))
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
                            if let count = value.as(Int.self) {
                                Text("\(count)")
                                    .font(.system(size: 8))
                                    .foregroundStyle(Theme.textMuted)
                            }
                        }
                    }
                }

                legend
            }
        }
    }

    private var legend: some View {
        HStack(spacing: 12) {
            let items: [(String, Color)] = [
                ("SSH fallidos", Theme.red),
                ("Escaneos SSH", Theme.amber),
                ("Firewall", Theme.orange),
                ("Web sospechosa", Theme.violet),
                ("Logins SSH", Theme.green),
            ]
            ForEach(items.indices, id: \.self) { index in
                HStack(spacing: 4) {
                    Circle().fill(items[index].1).frame(width: 5, height: 5)
                    Text(items[index].0)
                        .font(.system(size: 8))
                        .foregroundStyle(Theme.textMuted)
                }
            }
            Spacer(minLength: 0)
        }
    }

    private func securityXDomain(_ security: SecuritySnapshot) -> ClosedRange<Date> {
        let end = security.timeline.last?.date ?? Date()
        let start = end.addingTimeInterval(-store.securityRange.seconds)
        return start...end
    }

    // MARK: - Bots vs humanos

    private struct BotSlice: Identifiable {
        let id: String
        let count: Int
        let color: Color
    }

    private func botDonutPanel(_ security: SecuritySnapshot) -> some View {
        let summary = security.summary
        let slices: [BotSlice] = [
            BotSlice(id: "Bots", count: summary.bots, color: Theme.red),
            BotSlice(id: "Humanos", count: summary.humans, color: Theme.green),
            BotSlice(id: "Desconocidos", count: summary.unknown, color: Theme.textMuted),
        ].filter { $0.count > 0 }

        return Panel(title: "Bots vs humanos", systemImage: "person.crop.circle.badge.xmark") {
            if slices.isEmpty {
                EmptyStateView(
                    icon: "person.crop.circle",
                    title: "Sin IPs clasificadas",
                    message: "Todavía no hay actividad suficiente."
                )
            } else {
                HStack(spacing: 16) {
                    Chart(slices) { slice in
                        SectorMark(
                            angle: .value("IPs", slice.count),
                            innerRadius: .ratio(0.62),
                            angularInset: 2
                        )
                        .foregroundStyle(slice.color)
                        .cornerRadius(3)
                    }
                    .frame(width: 150, height: 150)
                    .overlay {
                        VStack(spacing: 1) {
                            Text(Fmt.integer(summary.uniqueIps))
                                .font(.system(size: 22, weight: .semibold, design: .rounded))
                                .monospacedDigit()
                                .foregroundStyle(Theme.textPrimary)
                            Text("IPs ÚNICAS")
                                .font(.system(size: 7, weight: .bold))
                                .tracking(0.7)
                                .foregroundStyle(Theme.textMuted)
                        }
                    }

                    VStack(alignment: .leading, spacing: 7) {
                        ForEach(slices) { slice in
                            HStack(spacing: 6) {
                                Circle().fill(slice.color).frame(width: 6, height: 6)
                                Text(slice.id)
                                    .font(.system(size: 10))
                                    .foregroundStyle(Theme.textSecondary)
                                Spacer()
                                Text(Fmt.integer(slice.count))
                                    .font(.system(size: 10, design: .monospaced))
                                    .foregroundStyle(Theme.textPrimary)
                            }
                        }
                    }
                }
            }
        }
    }

    // MARK: - Top IPs

    private func topIPsPanel(_ security: SecuritySnapshot) -> some View {
        Panel(title: "IPs con más actividad", systemImage: "globe") {
            if security.topIps.isEmpty {
                EmptyStateView(
                    icon: "network",
                    title: "Sin IPs",
                    message: "No hay eventos en el rango seleccionado."
                )
            } else {
                VStack(spacing: 0) {
                    ForEach(security.topIps.prefix(8)) { ip in
                        if ip.ip != security.topIps.first?.ip {
                            Divider().overlay(Theme.border)
                        }
                        HStack(alignment: .center, spacing: 8) {
                            Text(Fmt.flag(ip.countryCode))
                                .font(.system(size: 16))
                            VStack(alignment: .leading, spacing: 2) {
                                HStack(spacing: 6) {
                                    Text(ip.ip)
                                        .font(.system(size: 11, weight: .medium, design: .monospaced))
                                        .foregroundStyle(Theme.textPrimary)
                                    ClassificationBadge(classification: ip.classification)
                                }
                                Text(countryLine(ip))
                                    .font(.system(size: 8))
                                    .foregroundStyle(Theme.textMuted)
                                    .lineLimit(1)
                            }
                            Spacer(minLength: 4)
                            VStack(alignment: .trailing, spacing: 2) {
                                Text("\(ip.events) ev")
                                    .font(.system(size: 10, weight: .semibold, design: .monospaced))
                                    .foregroundStyle(Theme.textSecondary)
                                Text(Fmt.relative(ip.lastDate))
                                    .font(.system(size: 8))
                                    .foregroundStyle(Theme.textMuted)
                            }
                        }
                        .padding(.vertical, 8)
                    }
                }
            }
        }
    }

    private func countryLine(_ ip: SecurityTopIP) -> String {
        var parts: [String] = []
        if let country = ip.country, country != "Desconocido" { parts.append(country) }
        if let city = ip.city, !city.isEmpty { parts.append(city) }
        if let isp = ip.isp, !isp.isEmpty { parts.append(isp) }
        return parts.isEmpty ? "Sin geolocalizar" : parts.joined(separator: " · ")
    }

    // MARK: - Países

    private func countriesPanel(_ security: SecuritySnapshot) -> some View {
        let maxEvents = max(security.topCountries.map(\.events).max() ?? 1, 1)
        return Panel(title: "Países de origen", systemImage: "mappin.and.ellipse") {
            if security.topCountries.isEmpty {
                EmptyStateView(
                    icon: "map",
                    title: "Sin geolocalizaciones",
                    message: "Las IPs nuevas se enriquecen progresivamente."
                )
            } else {
                VStack(spacing: 9) {
                    ForEach(security.topCountries, id: \.countryCode) { country in
                        VStack(spacing: 3) {
                            HStack {
                                Text("\(Fmt.flag(country.countryCode)) \(country.country)")
                                    .font(.system(size: 10))
                                    .foregroundStyle(Theme.textSecondary)
                                Spacer()
                                Text("\(country.events) ev · \(country.ips) IPs")
                                    .font(.system(size: 8, design: .monospaced))
                                    .foregroundStyle(Theme.textMuted)
                            }
                            UsageBar(
                                percent: Double(country.events) / Double(maxEvents) * 100,
                                color: Theme.accent.opacity(0.7),
                                height: 4
                            )
                        }
                    }
                }
            }
        }
    }

    // MARK: - Amenazas

    private func threatsPanel(_ security: SecuritySnapshot) -> some View {
        Panel(title: "Indicadores de amenaza", systemImage: "exclamationmark.shield") {
            VStack(alignment: .leading, spacing: 12) {
                ThreatList(
                    title: "Usuarios objetivo",
                    icon: "terminal",
                    rows: security.topUsernames.map { ($0.username, $0.attempts) },
                    emptyText: "Sin intentos con usuario."
                )
                Divider().overlay(Theme.border)
                ThreatList(
                    title: "Puertos escaneados",
                    icon: "shield",
                    rows: security.topPorts.map { ("puerto \($0.port)", $0.attempts) },
                    emptyText: "Sin bloqueos de firewall."
                )
                Divider().overlay(Theme.border)
                ThreatList(
                    title: "Rutas escaneadas",
                    icon: "exclamationmark.triangle",
                    rows: security.topPaths.map { ($0.path, $0.attempts) },
                    emptyText: "Sin escaneos web."
                )
            }
        }
    }

    // MARK: - Eventos

    private func recentEventsPanel(_ security: SecuritySnapshot) -> some View {
        Panel(title: "Últimos eventos", systemImage: "list.bullet.rectangle") {
            if security.recentEvents.isEmpty {
                EmptyStateView(
                    icon: "clock",
                    title: "Sin eventos",
                    message: "Aún no se ha registrado actividad de seguridad."
                )
            } else {
                VStack(spacing: 0) {
                    ForEach(security.recentEvents.prefix(15)) { event in
                        if event.id != security.recentEvents.first?.id {
                            Divider().overlay(Theme.border)
                        }
                        HStack(alignment: .top, spacing: 8) {
                            Circle()
                                .fill(eventColor(event.kind))
                                .frame(width: 6, height: 6)
                                .padding(.top, 4)
                            VStack(alignment: .leading, spacing: 2) {
                                HStack {
                                    Text(event.kindLabel)
                                        .font(.system(size: 10, weight: .medium))
                                        .foregroundStyle(Theme.textSecondary)
                                    Spacer()
                                    Text(Fmt.relative(event.date))
                                        .font(.system(size: 8))
                                        .foregroundStyle(Theme.textMuted)
                                }
                                HStack(spacing: 4) {
                                    Text(Fmt.flag(event.countryCode))
                                        .font(.system(size: 10))
                                    Text(event.ip)
                                        .font(.system(size: 9, design: .monospaced))
                                        .foregroundStyle(Theme.textMuted)
                                    if let country = event.country, country != "Red local", country != "Desconocido" {
                                        Text("· \(country)")
                                            .font(.system(size: 8))
                                            .foregroundStyle(Theme.textMuted)
                                    }
                                }
                                Text(event.detail)
                                    .font(.system(size: 9))
                                    .foregroundStyle(Theme.textMuted)
                                    .lineLimit(2)
                            }
                        }
                        .padding(.vertical, 7)
                    }
                }
            }
        }
    }

    private func eventColor(_ kind: String) -> Color {
        switch kind {
        case "ssh_failed": return Theme.red
        case "ssh_success": return Theme.green
        case "ssh_scan": return Theme.amber
        case "firewall_block": return Theme.orange
        case "http_suspicious": return Theme.violet
        default: return Theme.textMuted
        }
    }

    // MARK: - Estados y ayuda

    private var loadingPanel: some View {
        Panel(title: "Cargando seguridad", systemImage: "shield") {
            HStack(spacing: 10) {
                ProgressView().tint(Theme.accent)
                Text("Consultando eventos del servidor…")
                    .font(.system(size: 11))
                    .foregroundStyle(Theme.textSecondary)
                Spacer()
            }
        }
    }

    private var disabledPanel: some View {
        Panel(title: "Monitor desactivado", systemImage: "shield.slash") {
            Text("Activa SECURITY_ENABLED=true en el .env del servidor y recrea el backend.")
                .font(.system(size: 11))
                .foregroundStyle(Theme.textSecondary)
        }
    }

    private func offlinePanel(_ message: String) -> some View {
        Panel(title: "Sin datos de seguridad", systemImage: "wifi.exclamationmark") {
            Text(message)
                .font(.system(size: 11))
                .foregroundStyle(Theme.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
            Button("Reintentar") {
                Task { await store.loadSecurity() }
            }
            .buttonStyle(GhostButtonStyle())
        }
    }

    private func sourcesHelpPanel(_ security: SecuritySnapshot) -> some View {
        Panel(title: "Fuentes sin datos", systemImage: "exclamationmark.triangle") {
            VStack(alignment: .leading, spacing: 8) {
                if security.sources.ssh.available != true {
                    sourceHint(
                        title: "SSH",
                        text: "Monta /var/log en el backend y verifica /var/log/auth.log (o secure)."
                    )
                }
                if security.sources.firewall.available != true {
                    sourceHint(
                        title: "Firewall",
                        text: "Activa el logging con `sudo ufw logging on` en el servidor."
                    )
                }
                if security.sources.web.available != true {
                    sourceHint(
                        title: "Web",
                        text: "El volumen nginx-logs debe estar montado; recrea backend y frontend."
                    )
                }
            }
        }
    }

    private func sourceHint(title: String, text: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(title)
                .font(.system(size: 9, weight: .semibold))
                .foregroundStyle(Theme.textSecondary)
            Text(text)
                .font(.system(size: 9))
                .foregroundStyle(Theme.textMuted)
                .fixedSize(horizontal: false, vertical: true)
        }
    }
}
