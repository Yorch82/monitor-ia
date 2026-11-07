import Foundation

// ============================================================================
// Modelos de telemetría — espejo exacto de los dataclasses del backend.
// El JSONDecoder usa .convertFromSnakeCase, por eso los nombres son camelCase.
// ============================================================================

enum TelemetryMode: String, Codable {
    case simulation
    case live
}

enum ContextLevel: String, Codable {
    case ok
    case warning
    case critical
    case unavailable = "none"
}

enum InferenceHealth: String, Codable {
    case online
    case offline
    case unknown
}

enum AlertSeverity: String, Codable {
    case warning
    case critical
}

struct AlertItem: Codable, Identifiable, Hashable {
    let id: String
    let severity: AlertSeverity
    let message: String
    let value: Double
    let threshold: Double
    let ts: Double

    var date: Date { Date(timeIntervalSince1970: ts) }
}

struct RequestUsage: Codable, Identifiable, Hashable {
    let ts: Double
    let inputTokens: Int
    let outputTokens: Int
    let durationS: Double
    let model: String?
    let totalTokens: Int
    let tokensPerSecond: Double

    var id: Double { ts }
    var date: Date { Date(timeIntervalSince1970: ts) }
}

struct ContextState: Codable, Hashable {
    let available: Bool
    let usedTokens: Int?
    let maxTokens: Int?
    let percent: Double?
    let level: ContextLevel
    let source: String
}

struct TokensSnapshot: Codable, Hashable {
    let source: String
    let inputTokens: Int
    let outputTokens: Int
    let totalTokens: Int
    let requests: Int
    let instantInputPerS: Double
    let instantOutputPerS: Double
    let movingAvgOutputPerS: Double
    let lastRequest: RequestUsage?
    let recentRequests: [RequestUsage]
    let context: ContextState
}

struct GpuReading: Codable, Identifiable, Hashable {
    let index: Int
    let name: String
    let vendor: String
    let utilizationPct: Double?
    let memoryUsedMb: Double?
    let memoryTotalMb: Double?
    let memoryPct: Double?
    let temperatureC: Double?
    let fanPct: Double?
    let powerW: Double?
    let powerLimitW: Double?
    let powerPct: Double?

    var id: Int { index }
}

struct HardwareStatus: Codable, Hashable {
    let gpuAvailable: Bool
    let gpuError: String?
    let provider: String
    let mode: TelemetryMode
}

struct PowerSnapshot: Codable, Hashable {
    let currentW: Double?
    let limitW: Double?
    let percent: Double?
    let energySessionWh: Double
    let energySessionKwh: Double
    let available: Bool
}

struct CostSnapshot: Codable, Hashable {
    let pricePerKwh: Double
    let sessionCost: Double
    let costPerHour: Double?
    let projectionDay: Double?
    let projectionMonth: Double?
    let costPer1kTokens: Double?
    let dailyCost: Double
    let dailyLimit: Double?
    let dailyPct: Double?
}

struct SystemReading: Codable, Hashable {
    let cpuPct: Double?
    let cpuCount: Int?
    let ramUsedGb: Double?
    let ramTotalGb: Double?
    let ramPct: Double?
    let swapUsedGb: Double?
    let swapTotalGb: Double?
    let swapPct: Double?
    let uptimeS: Double?
}

struct InferenceStatus: Codable, Hashable {
    let status: InferenceHealth
    let engine: String
    let model: String
    let latencyMs: Double?
    let error: String?
    let contextHintTokens: Int?
    let contextHintSource: String
}

struct TelemetrySnapshot: Codable {
    let ts: Double
    let tsIso: String?
    let mode: TelemetryMode
    let intervalS: Double
    let tokens: TokensSnapshot
    let gpus: [GpuReading]
    let hardware: HardwareStatus
    let power: PowerSnapshot
    let cost: CostSnapshot
    let system: SystemReading
    let inference: InferenceStatus
    let alerts: [AlertItem]
    let gpuAvgPct: Double?
    let gpuTempMaxC: Double?
    let vramAvgPct: Double?

    var date: Date { Date(timeIntervalSince1970: ts) }
}

struct TelemetryEnvelope: Codable {
    let snapshot: TelemetrySnapshot?
    let uptimeS: Double?
}

// ============================================================================
// Puntos de gráfica (histórico y vivo comparten la misma forma)
// ============================================================================

struct ChartPoint: Codable, Identifiable, Hashable {
    let t: Int
    let inputPerS: Double?
    let outputPerS: Double?
    let movingAvgPerS: Double?
    let contextPct: Double?
    let gpuPct: Double?
    let vramPct: Double?
    let gpuTempC: Double?
    let powerW: Double?
    let ramPct: Double?
    let cpuPct: Double?
    let costPerHour: Double?
    let inputTotal: Int
    let outputTotal: Int

    var id: Int { t }
    var date: Date { Date(timeIntervalSince1970: Double(t) / 1000.0) }
}

struct HistoryResponse: Codable {
    let range: String
    let bucketSeconds: Int
    let points: [ChartPoint]
}

// ============================================================================
// Rangos y estados de conexión
// ============================================================================

enum ChartRange: String, CaseIterable, Identifiable {
    case minute = "1m"
    case quarterHour = "15m"
    case hour = "1h"
    case day = "24h"

    var id: String { rawValue }

    var shortLabel: String {
        switch self {
        case .minute: return "1 min"
        case .quarterHour: return "15 min"
        case .hour: return "1 h"
        case .day: return "24 h"
        }
    }

    var seconds: TimeInterval {
        switch self {
        case .minute: return 60
        case .quarterHour: return 15 * 60
        case .hour: return 60 * 60
        case .day: return 24 * 60 * 60
        }
    }
}

enum ConnectionState {
    case connecting
    case live
    case reconnecting
    case offline

    var label: String {
        switch self {
        case .connecting: return "CONECTANDO"
        case .live: return "EN VIVO"
        case .reconnecting: return "RECONECTANDO"
        case .offline: return "SIN CONEXIÓN"
        }
    }
}

// MARK: - Snapshot → punto de gráfica

extension TelemetrySnapshot {
    func toChartPoint() -> ChartPoint {
        ChartPoint(
            t: Int(ts * 1000),
            inputPerS: tokens.instantInputPerS,
            outputPerS: tokens.instantOutputPerS,
            movingAvgPerS: tokens.movingAvgOutputPerS,
            contextPct: tokens.context.percent,
            gpuPct: gpuAvgPct,
            vramPct: vramAvgPct,
            gpuTempC: gpuTempMaxC,
            powerW: power.currentW,
            ramPct: system.ramPct,
            cpuPct: system.cpuPct,
            costPerHour: cost.costPerHour,
            inputTotal: tokens.inputTokens,
            outputTotal: tokens.outputTokens
        )
    }
}
