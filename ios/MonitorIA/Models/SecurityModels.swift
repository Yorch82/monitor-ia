import Foundation

// ============================================================================
// Modelos de la pestaña Seguridad (GET /api/security?range=1h|24h|7d)
// ============================================================================

enum SecurityRange: String, CaseIterable, Identifiable {
    case hour = "1h"
    case day = "24h"
    case week = "7d"

    var id: String { rawValue }

    var label: String {
        switch self {
        case .hour: return "1 h"
        case .day: return "24 h"
        case .week: return "7 días"
        }
    }

    var seconds: TimeInterval {
        switch self {
        case .hour: return 3_600
        case .day: return 86_400
        case .week: return 7 * 86_400
        }
    }

    var chartFormat: DateFormatter {
        switch self {
        case .hour, .day:
            return Fmt.securityTimeFormatter
        case .week:
            return Fmt.securityDateFormatter
        }
    }
}

enum SecurityClassification: String, Codable {
    case bot
    case human
    case unknown
}

enum SecuritySeverity: String, Codable {
    case info
    case warning
    case critical
}

struct SecurityLogSource: Codable {
    let available: Bool?
    let paths: [String]?
    let error: String?
}

struct GeoIPSource: Codable {
    let enabled: Bool
    let provider: String
    let lookupsOk: Int
    let lookupsFailed: Int
}

struct SecuritySources: Codable {
    let enabled: Bool
    let ssh: SecurityLogSource
    let firewall: SecurityLogSource
    let web: SecurityLogSource
    let geoip: GeoIPSource
    let retentionHours: Int
}

struct SecurityLastLogin: Codable, Hashable {
    let ts: Double
    let ip: String
    let username: String?
    let countryCode: String?
    let country: String?

    var date: Date { Date(timeIntervalSince1970: ts) }
}

struct SecurityPortCount: Codable, Hashable {
    let port: Int
    let attempts: Int
}

struct SecurityCountry: Codable, Hashable {
    let countryCode: String
    let country: String
    let events: Int
    let ips: Int
}

struct SecuritySummary: Codable {
    let totalEvents: Int
    let sshFailed: Int
    let sshSuccess: Int
    let sshScan: Int
    let firewallBlocks: Int
    let webSuspicious: Int
    let uniqueIps: Int
    let countries: Int
    let bots: Int
    let humans: Int
    let unknown: Int
    let botPct: Double?
    let eventsPerHour: Double
    let lastSshSuccess: SecurityLastLogin?
    let topPort: SecurityPortCount?
    let topCountry: SecurityCountry?
}

struct SecurityTimelinePoint: Codable, Identifiable, Hashable {
    let t: Int
    let sshFailed: Int
    let sshSuccess: Int
    let sshScan: Int
    let firewallBlocks: Int
    let webSuspicious: Int

    var id: Int { t }
    var date: Date { Date(timeIntervalSince1970: Double(t) / 1000.0) }
}

struct SecurityTopIP: Codable, Identifiable, Hashable {
    let ip: String
    let events: Int
    let lastTs: Double
    let firstTs: Double
    let sshFailed: Int
    let sshSuccess: Int
    let sshScan: Int
    let firewallBlocks: Int
    let webSuspicious: Int
    let countryCode: String?
    let country: String?
    let city: String?
    let isp: String?
    let classification: SecurityClassification

    var id: String { ip }
    var lastDate: Date { Date(timeIntervalSince1970: lastTs) }
}

struct SecurityUsername: Codable, Identifiable, Hashable {
    let username: String
    let attempts: Int
    var id: String { username }
}

struct SecurityPort: Codable, Identifiable, Hashable {
    let port: Int
    let attempts: Int
    var id: Int { port }
}

struct SecurityPath: Codable, Identifiable, Hashable {
    let path: String
    let attempts: Int
    var id: String { path }
}

struct SecurityEvent: Codable, Identifiable, Hashable {
    let ts: Double
    let kind: String
    let ip: String
    let classification: SecurityClassification
    let severity: SecuritySeverity
    let username: String?
    let path: String?
    let port: Int?
    let detail: String
    let userAgent: String?
    let countryCode: String?
    let country: String?
    let city: String?

    var id: String { "\(ts)-\(kind)-\(ip)-\(path ?? "")-\(port ?? 0)" }
    var date: Date { Date(timeIntervalSince1970: ts) }
    var kindLabel: String {
        switch kind {
        case "ssh_failed": return "SSH fallido"
        case "ssh_success": return "Login SSH"
        case "ssh_scan": return "Escaneo SSH"
        case "firewall_block": return "Firewall"
        case "http_suspicious": return "Web sospechosa"
        default: return kind
        }
    }
}

struct SecuritySnapshot: Codable {
    let generatedAt: Double
    let range: String
    let enabled: Bool
    let sources: SecuritySources
    let summary: SecuritySummary
    let timeline: [SecurityTimelinePoint]
    let topIps: [SecurityTopIP]
    let topCountries: [SecurityCountry]
    let topUsernames: [SecurityUsername]
    let topPorts: [SecurityPort]
    let topPaths: [SecurityPath]
    let recentEvents: [SecurityEvent]
}
