import Foundation

// ============================================================================
// Modelos de la pestaña Refrigeración (GET /api/cooling).
// ============================================================================

struct CoolingControl: Codable {
    let enabled: Bool
    let writable: Bool
    let released: Bool
    let profile: String
    let emergencyActive: Bool
    let minPwmPct: Double
    let emergencyTempC: Double
    let emergencyReleaseC: Double
    let restoreOnExit: Bool
    let lastError: String?
    let note: String
}

struct CoolingTemperature: Codable, Identifiable, Hashable {
    let id: String
    let label: String
    let source: String
    let valueC: Double
    let chip: String
}

struct CoolingFan: Codable, Identifiable, Hashable {
    let id: String
    let label: String
    let kind: String
    let source: String
    let rpm: Int?
    let pwmPct: Double?
    let controllable: Bool
    let minPwmPct: Double
    let lastError: String?
}

struct CoolingProfileInfo: Codable, Identifiable {
    let id: String
    let label: String
    let description: String
    let targetPwmPct: Double?
}

struct CoolingSummary: Codable {
    let cpuTempC: Double?
    let gpuTempC: Double?
    let maxTempC: Double?
    let fanCount: Int
    let controllableFans: Int
    let avgFanRpm: Double?
}

struct CoolingSnapshot: Codable {
    let updatedAt: Double
    let mode: String
    let available: Bool
    let control: CoolingControl
    let summary: CoolingSummary
    let temperatures: [CoolingTemperature]
    let fans: [CoolingFan]
    let profiles: [CoolingProfileInfo]

    var updatedDate: Date { Date(timeIntervalSince1970: updatedAt) }
    var isSimulation: Bool { mode == "simulation" }
}

struct CoolingProfileUpdate: Encodable {
    let profile: String
}

struct CoolingFanUpdate: Encodable {
    let pwmPct: Double
}
