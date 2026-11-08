import Combine
import Foundation
import UIKit

// ============================================================================
// Store central de la app: WebSocket en vivo, histórico, seguridad y ajustes.
// Toda la mutación ocurre en el MainActor; la UI observa @Published.
// ============================================================================

@MainActor
final class MonitorStore: ObservableObject {
    static let serverURLKey = "monitor.serverURL"
    static let defaultServerURL = "http://192.168.1.35:8080"

    // Servidor / conexión
    @Published private(set) var serverURL: String
    @Published private(set) var connection: ConnectionState = .connecting
    @Published private(set) var lastError: String?

    // Telemetría
    @Published private(set) var snapshot: TelemetrySnapshot?
    @Published private(set) var points: [ChartPoint] = []
    @Published private(set) var range: ChartRange = .quarterHour
    @Published private(set) var isHistoryLoading = false

    // Seguridad
    @Published private(set) var securityRange: SecurityRange = .day
    @Published private(set) var security: SecuritySnapshot?
    @Published private(set) var securityError: String?
    @Published private(set) var isSecurityLoading = false

    // Ajustes
    @Published private(set) var settings: PublicSettings?
    @Published private(set) var settingsError: String?
    @Published private(set) var isSavingSettings = false

    // Refrigeración
    @Published private(set) var cooling: CoolingSnapshot?
    @Published private(set) var coolingError: String?
    @Published private(set) var isCoolingLoading = false
    @Published private(set) var isCoolingUpdating = false

    private let session: URLSession
    private let defaults: UserDefaults
    private let decoder: JSONDecoder

    private var wsTask: URLSessionWebSocketTask?
    private var receiveTask: Task<Void, Never>?
    private var retryTask: Task<Void, Never>?
    private var reconnectAttempt = 0
    private var socketGeneration = 0
    private var intentionalStop = true
    private var hasReceivedFrame = false
    private var previousAlertIds: Set<String> = []
    private var started = false

    init() {
        let configuration = URLSessionConfiguration.default
        configuration.timeoutIntervalForRequest = 15
        configuration.timeoutIntervalForResource = 45
        configuration.waitsForConnectivity = false
        session = URLSession(configuration: configuration)

        defaults = .standard
        serverURL = UserDefaults.standard.string(forKey: Self.serverURLKey) ?? Self.defaultServerURL

        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        self.decoder = decoder
    }

    private var api: APIClient? {
        APIClient(serverString: serverURL, session: session)
    }

    var serverDisplay: String {
        URL(string: serverURL)?.host ?? serverURL
    }

    var isLive: Bool { connection == .live }

    // MARK: - Ciclo de vida

    func start() {
        guard !started else { return }
        started = true
        connectSocket()
        Task {
            await loadSnapshot()
            await loadHistory()
        }
    }

    func appDidEnterBackground() {
        intentionalStop = true
        socketGeneration += 1
        receiveTask?.cancel()
        receiveTask = nil
        retryTask?.cancel()
        retryTask = nil
        wsTask?.cancel(with: .goingAway, reason: nil)
        wsTask = nil
        connection = .offline
    }

    func appWillEnterForeground() {
        guard started else { return }
        connectSocket()
        Task {
            await loadSnapshot()
            await loadHistory()
        }
    }

    func refreshDashboard() async {
        await loadSnapshot()
        await loadHistory()
    }

    func setRange(_ newRange: ChartRange) {
        guard newRange != range else { return }
        range = newRange
        trimPoints()
        Task { await loadHistory() }
    }

    func setSecurityRange(_ newRange: SecurityRange) {
        guard newRange != securityRange else { return }
        securityRange = newRange
        Task { await loadSecurity() }
    }

    // MARK: - Refrigeración

    func loadCooling() async {
        guard let api, !isCoolingLoading else { return }
        isCoolingLoading = true
        do {
            cooling = try await api.get("/api/cooling")
            coolingError = nil
        } catch {
            coolingError = friendly(error)
        }
        isCoolingLoading = false
    }

    @discardableResult
    func applyCoolingProfile(_ profile: String) async -> Bool {
        guard let api else { return false }
        isCoolingUpdating = true
        defer { isCoolingUpdating = false }
        do {
            let snapshot: CoolingSnapshot = try await api.send(
                "PUT", "/api/cooling/profile", body: CoolingProfileUpdate(profile: profile)
            )
            cooling = snapshot
            coolingError = nil
            return true
        } catch {
            coolingError = friendly(error)
            return false
        }
    }

    @discardableResult
    func applyFanPWM(fanID: String, pwmPct: Double) async -> Bool {
        guard let api else { return false }
        isCoolingUpdating = true
        defer { isCoolingUpdating = false }
        do {
            let encoded = fanID.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? fanID
            let snapshot: CoolingSnapshot = try await api.send(
                "PUT", "/api/cooling/fans/\(encoded)", body: CoolingFanUpdate(pwmPct: pwmPct)
            )
            cooling = snapshot
            coolingError = nil
            return true
        } catch {
            coolingError = friendly(error)
            return false
        }
    }

    @discardableResult
    func releaseCoolingToBIOS() async -> Bool {
        guard let api else { return false }
        isCoolingUpdating = true
        defer { isCoolingUpdating = false }
        do {
            let snapshot: CoolingSnapshot = try await api.post("/api/cooling/release")
            cooling = snapshot
            coolingError = nil
            return true
        } catch {
            coolingError = friendly(error)
            return false
        }
    }

    // MARK: - WebSocket

    private func connectSocket() {
        guard started else { return }
        guard let url = api?.websocketURL else {
            connection = .offline
            lastError = APIError.invalidServerURL.localizedDescription
            return
        }

        socketGeneration += 1
        let generation = socketGeneration
        intentionalStop = false
        receiveTask?.cancel()
        receiveTask = nil
        retryTask?.cancel()
        retryTask = nil

        connection = reconnectAttempt == 0 ? .connecting : .reconnecting
        let task = session.webSocketTask(with: url)
        wsTask = task
        task.resume()
        listen(on: task, generation: generation)
    }

    private func listen(on task: URLSessionWebSocketTask, generation: Int) {
        receiveTask = Task { [weak self] in
            guard let self else { return }
            while !Task.isCancelled {
                do {
                    let message = try await task.receive()
                    guard !Task.isCancelled, generation == self.socketGeneration else { return }
                    switch message {
                    case .string(let text):
                        self.handleFrame(text: text)
                    case .data(let data):
                        if let text = String(data: data, encoding: .utf8) {
                            self.handleFrame(text: text)
                        }
                    @unknown default:
                        break
                    }
                } catch {
                    guard generation == self.socketGeneration else { return }
                    self.handleSocketFailure(error)
                    return
                }
            }
        }
    }

    private func handleFrame(text: String) {
        guard let data = text.data(using: .utf8),
              let frame = try? decoder.decode(TelemetrySnapshot.self, from: data) else {
            return
        }

        let firstFrame = snapshot == nil
        let previousIds = previousAlertIds
        snapshot = frame
        connection = .live
        lastError = nil
        reconnectAttempt = 0
        hasReceivedFrame = true
        appendLivePoint(frame.toChartPoint())

        if !firstFrame,
           frame.alerts.contains(where: {
               $0.severity == .critical && !previousIds.contains($0.id)
           }) {
            UINotificationFeedbackGenerator().notificationOccurred(.warning)
        }
        previousAlertIds = Set(frame.alerts.map(\.id))
    }

    private func handleSocketFailure(_ error: Error?) {
        guard !intentionalStop, started else { return }
        connection = reconnectAttempt >= 2 ? .offline : .reconnecting
        lastError = snapshot == nil ? friendly(error) : "Conexión perdida. Reintentando…"
        scheduleReconnect()
    }

    private func scheduleReconnect() {
        guard started, !intentionalStop else { return }
        retryTask?.cancel()
        let attempt = reconnectAttempt
        reconnectAttempt = min(reconnectAttempt + 1, 10)
        if attempt >= 3 { connection = .offline }
        let delay = min(10.0, 0.7 * pow(1.7, Double(attempt)))
        retryTask = Task { [weak self] in
            try? await Task.sleep(nanoseconds: UInt64(delay * 1_000_000_000))
            guard !Task.isCancelled, let self, !self.intentionalStop else { return }
            self.connectSocket()
        }
    }

    // MARK: - Telemetría

    private func loadSnapshot() async {
        guard let api else {
            lastError = APIError.invalidServerURL.localizedDescription
            return
        }
        do {
            let envelope: TelemetryEnvelope = try await api.get("/api/telemetry")
            if let snapshot = envelope.snapshot {
                self.snapshot = snapshot
                lastError = nil
                if !hasReceivedFrame {
                    appendLivePoint(snapshot.toChartPoint())
                }
            }
        } catch {
            lastError = friendly(error)
        }
    }

    private func loadHistory() async {
        guard let api, !isHistoryLoading else { return }
        isHistoryLoading = true
        let requestedRange = range
        do {
            let response: HistoryResponse = try await api.get(
                "/api/history",
                query: [URLQueryItem(name: "range", value: requestedRange.rawValue)]
            )
            guard requestedRange == range else {
                isHistoryLoading = false
                return
            }
            let lastHistoryT = response.points.last?.t ?? 0
            let liveTail = points.filter { $0.t > lastHistoryT }
            var merged = response.points + liveTail
            merged.sort { $0.t < $1.t }
            let cutoff = Int(Date().timeIntervalSince1970 * 1000)
                - Int(requestedRange.seconds * 1000)
            merged = merged.filter { $0.t >= cutoff }
            points = Array(merged.suffix(3_500))
        } catch {
            if requestedRange == range {
                lastError = friendly(error)
            }
        }
        isHistoryLoading = false
        if requestedRange != range {
            // El usuario cambió de rango mientras había una petición en vuelo:
            // descartamos la respuesta antigua y pedimos la del rango actual.
            await loadHistory()
        }
    }

    private func appendLivePoint(_ point: ChartPoint) {
        let bucket = range.bucketMilliseconds
        let aligned = point.t / bucket * bucket
        if let last = points.last {
            let lastAligned = last.t / bucket * bucket
            if aligned == lastAligned {
                points[points.count - 1] = point
                return
            }
            if point.t < last.t { return }
        }
        points.append(point)
        trimPoints()
    }

    private func trimPoints() {
        let cutoff = Int(Date().timeIntervalSince1970 * 1000) - Int(range.seconds * 1000)
        if let first = points.first, first.t < cutoff {
            points = points.filter { $0.t >= cutoff }
        }
        if points.count > 3_500 {
            points = Array(points.suffix(3_500))
        }
    }

    // MARK: - Seguridad

    func loadSecurity() async {
        guard let api, !isSecurityLoading else { return }
        isSecurityLoading = true
        let requestedRange = securityRange
        do {
            let response: SecuritySnapshot = try await api.get(
                "/api/security",
                query: [URLQueryItem(name: "range", value: requestedRange.rawValue)]
            )
            if requestedRange == securityRange {
                security = response
                securityError = nil
            }
        } catch {
            if requestedRange == securityRange {
                securityError = friendly(error)
            }
        }
        isSecurityLoading = false
        if requestedRange != securityRange {
            await loadSecurity()
        }
    }

    // MARK: - Ajustes

    func loadSettings() async {
        guard let api else {
            settingsError = APIError.invalidServerURL.localizedDescription
            return
        }
        do {
            settings = try await api.get("/api/settings")
            settingsError = nil
        } catch {
            settingsError = friendly(error)
        }
    }

    @discardableResult
    func saveSettings(_ update: SettingsUpdate) async -> Bool {
        guard let api else { return false }
        isSavingSettings = true
        defer { isSavingSettings = false }
        do {
            let saved: PublicSettings = try await api.send("PUT", "/api/settings", body: update)
            settings = saved
            settingsError = nil
            return true
        } catch {
            settingsError = friendly(error)
            return false
        }
    }

    @discardableResult
    func restoreDefaultSettings() async -> Bool {
        guard let api else { return false }
        isSavingSettings = true
        defer { isSavingSettings = false }
        do {
            let restored: PublicSettings = try await api.post("/api/settings/reset")
            settings = restored
            settingsError = nil
            return true
        } catch {
            settingsError = friendly(error)
            return false
        }
    }

    @discardableResult
    func resetSession() async -> Bool {
        guard let api else { return false }
        do {
            try await api.postIgnoringResponse("/api/session/reset")
            await refreshDashboard()
            return true
        } catch {
            lastError = friendly(error)
            return false
        }
    }

    func downloadCSV(range: ChartRange) async throws -> URL {
        guard let api else { throw APIError.invalidServerURL }
        return try await api.downloadCSV(range: range)
    }

    // MARK: - Cambio de servidor

    @discardableResult
    func updateServerURL(_ raw: String) async -> Bool {
        guard let normalized = APIClient.normalizeServer(raw) else {
            lastError = APIError.invalidServerURL.localizedDescription
            return false
        }
        var value = normalized.absoluteString
        while value.hasSuffix("/") { value.removeLast() }

        serverURL = value
        defaults.set(value, forKey: Self.serverURLKey)

        resetConnectionState()
        connectSocket()
        await loadSnapshot()
        await loadHistory()
        return true
    }

    private func resetConnectionState() {
        intentionalStop = true
        socketGeneration += 1
        receiveTask?.cancel()
        receiveTask = nil
        retryTask?.cancel()
        retryTask = nil
        wsTask?.cancel(with: .goingAway, reason: nil)
        wsTask = nil
        snapshot = nil
        points = []
        security = nil
        settings = nil
        cooling = nil
        connection = .connecting
        reconnectAttempt = 0
        hasReceivedFrame = false
        previousAlertIds = []
        lastError = nil
    }

    // MARK: - Errores

    private func friendly(_ error: Error?) -> String {
        guard let error else { return "Error de conexión" }
        if let apiError = error as? APIError {
            return apiError.localizedDescription
        }
        if let urlError = error as? URLError {
            switch urlError.code {
            case .cannotConnectToHost, .cannotFindHost, .networkConnectionLost,
                 .timedOut, .notConnectedToInternet, .secureConnectionFailed:
                return "No se puede conectar con \(serverURL). Comprueba red/VPN y la URL del servidor."
            default:
                return urlError.localizedDescription
            }
        }
        return error.localizedDescription
    }
}
