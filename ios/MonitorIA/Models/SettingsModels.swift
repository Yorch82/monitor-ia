import Foundation

// ============================================================================
// Settings de la API (GET/PUT /api/settings). La API key nunca se devuelve.
// ============================================================================

struct AlertThresholds: Codable, Equatable {
    var contextPct: Double
    var gpuTempC: Double
    var vramPct: Double
    var ramPct: Double
    var dailyCostEur: Double
}

struct PublicSettings: Codable, Equatable {
    var simulationMode: Bool
    var refreshIntervalMs: Int
    var pricePerKwh: Double
    var inferenceBaseUrl: String
    var inferenceMetricsUrl: String
    var inferenceApiKeySet: Bool
    var inferenceModel: String
    var contextWindow: Int
    var tokenSource: String
    var gpuProvider: String
    var webhookUrl: String
    var historyRetentionHours: Int
    var thresholds: AlertThresholds
}

/// Payload de actualización parcial hacia el backend.
struct SettingsUpdate: Encodable {
    var simulationMode: Bool
    var refreshIntervalMs: Int
    var pricePerKwh: Double
    var inferenceBaseUrl: String
    var inferenceMetricsUrl: String
    var inferenceModel: String
    var contextWindow: Int
    var tokenSource: String
    var gpuProvider: String
    var webhookUrl: String
    var historyRetentionHours: Int
    var thresholds: AlertThresholds
    var inferenceApiKey: String?
}

/// Borrador editable para la pantalla de ajustes.
struct SettingsDraft {
    var simulationMode: Bool = true
    var refreshIntervalMs: Int = 1000
    var pricePerKwh: Double = 0.15
    var inferenceBaseUrl: String = ""
    var inferenceMetricsUrl: String = ""
    var inferenceModel: String = "local-model"
    var contextWindow: Int = 8192
    var tokenSource: String = "auto"
    var gpuProvider: String = "auto"
    var webhookUrl: String = ""
    var historyRetentionHours: Int = 24
    var contextPct: Double = 90
    var gpuTempC: Double = 80
    var vramPct: Double = 95
    var ramPct: Double = 90
    var dailyCostEur: Double = 1
    var apiKey: String = ""
    var clearApiKey: Bool = false

    init() {}

    init(settings: PublicSettings) {
        simulationMode = settings.simulationMode
        refreshIntervalMs = settings.refreshIntervalMs
        pricePerKwh = settings.pricePerKwh
        inferenceBaseUrl = settings.inferenceBaseUrl
        inferenceMetricsUrl = settings.inferenceMetricsUrl
        inferenceModel = settings.inferenceModel
        contextWindow = settings.contextWindow
        tokenSource = settings.tokenSource
        gpuProvider = settings.gpuProvider
        webhookUrl = settings.webhookUrl
        historyRetentionHours = settings.historyRetentionHours
        contextPct = settings.thresholds.contextPct
        gpuTempC = settings.thresholds.gpuTempC
        vramPct = settings.thresholds.vramPct
        ramPct = settings.thresholds.ramPct
        dailyCostEur = settings.thresholds.dailyCostEur
    }

    func update() -> SettingsUpdate {
        SettingsUpdate(
            simulationMode: simulationMode,
            refreshIntervalMs: refreshIntervalMs,
            pricePerKwh: pricePerKwh,
            inferenceBaseUrl: inferenceBaseUrl,
            inferenceMetricsUrl: inferenceMetricsUrl,
            inferenceModel: inferenceModel,
            contextWindow: contextWindow,
            tokenSource: tokenSource,
            gpuProvider: gpuProvider,
            webhookUrl: webhookUrl,
            historyRetentionHours: historyRetentionHours,
            thresholds: AlertThresholds(
                contextPct: contextPct,
                gpuTempC: gpuTempC,
                vramPct: vramPct,
                ramPct: ramPct,
                dailyCostEur: dailyCostEur
            ),
            inferenceApiKey: clearApiKey ? "" : (apiKey.isEmpty ? nil : apiKey)
        )
    }
}

// Añadimos el bucket temporal al rango de gráficas (iOS).
extension ChartRange {
    var bucketMilliseconds: Int {
        switch self {
        case .minute: return 1_000
        case .quarterHour: return 4_000
        case .hour: return 12_000
        case .day: return 60_000
        }
    }
}
