import Foundation

// ============================================================================
// Formateadores localizados (es-ES) para toda la interfaz.
// ============================================================================

enum Fmt {
    static let locale = Locale(identifier: "es_ES")

    static let timeSecondsFormatter: DateFormatter = makeFormatter("HH:mm:ss")
    static let timeMinutesFormatter: DateFormatter = makeFormatter("HH:mm")
    static let securityTimeFormatter: DateFormatter = makeFormatter("HH:mm")
    static let securityDateFormatter: DateFormatter = makeFormatter("dd/MM HH:mm")

    private static func makeFormatter(_ format: String) -> DateFormatter {
        let formatter = DateFormatter()
        formatter.locale = locale
        formatter.timeZone = .current
        formatter.dateFormat = format
        return formatter
    }

    private static let relativeFormatter: RelativeDateTimeFormatter = {
        let formatter = RelativeDateTimeFormatter()
        formatter.locale = Locale(identifier: "es_ES")
        formatter.unitsStyle = .abbreviated
        return formatter
    }()

    // MARK: - Números

    static func number(_ value: Double?, maxDigits: Int = 1) -> String {
        guard let value, value.isFinite else { return "—" }
        return value.formatted(
            .number.locale(locale).precision(.fractionLength(0...maxDigits))
        )
    }

    static func integer(_ value: Int?) -> String {
        guard let value else { return "—" }
        return value.formatted(.number.locale(locale))
    }

    static func compact(_ value: Int?) -> String {
        guard let value else { return "—" }
        let absolute = abs(value)
        let sign = value < 0 ? "-" : ""
        if absolute >= 1_000_000 {
            let millions = Double(absolute) / 1_000_000
            return sign + millions.formatted(.number.locale(locale).precision(.fractionLength(0...1))) + "M"
        }
        if absolute >= 1_000 {
            let thousands = Double(absolute) / 1_000
            return sign + thousands.formatted(.number.locale(locale).precision(.fractionLength(0...1))) + "k"
        }
        return integer(value)
    }

    static func percent(_ value: Double?, maxDigits: Int = 0) -> String {
        guard let value, value.isFinite else { return "—" }
        return number(value, maxDigits: maxDigits) + "%"
    }

    static func euro(_ value: Double?, digits: Int = 2) -> String {
        guard let value, value.isFinite else { return "—" }
        return value.formatted(
            .currency(code: "EUR").locale(locale).precision(.fractionLength(0...digits))
        )
    }

    static func gigabytes(_ megabytes: Double?) -> String {
        guard let megabytes else { return "—" }
        return (megabytes / 1024.0).formatted(
            .number.locale(locale).precision(.fractionLength(0...1))
        ) + " GB"
    }

    static func gigabytesFromGB(_ gigabytes: Double?) -> String {
        guard let gigabytes else { return "—" }
        return gigabytes.formatted(
            .number.locale(locale).precision(.fractionLength(0...1))
        ) + " GB"
    }

    static func milliseconds(_ value: Double?) -> String {
        guard let value else { return "—" }
        return number(value, maxDigits: 0) + " ms"
    }

    static func uptime(_ seconds: Double?) -> String {
        guard let seconds, seconds.isFinite, seconds >= 0 else { return "—" }
        let total = Int(seconds)
        let days = total / 86_400
        let hours = (total % 86_400) / 3_600
        let minutes = (total % 3_600) / 60
        if days > 0 { return "\(days)d \(hours)h" }
        if hours > 0 { return "\(hours)h \(minutes)m" }
        return "\(minutes)m \(total % 60)s"
    }

    static func epoch(_ value: Double?) -> String {
        guard let value else { return "—" }
        return timeSecondsFormatter.string(from: Date(timeIntervalSince1970: value))
    }

    static func time(_ date: Date, range: ChartRange) -> String {
        range == .day ? timeMinutesFormatter.string(from: date) : timeSecondsFormatter.string(from: date)
    }

    static func securityTime(_ date: Date, range: SecurityRange) -> String {
        range.chartFormat.string(from: date)
    }

    static func relative(_ date: Date) -> String {
        relativeFormatter.localizedString(for: date, relativeTo: Date())
    }

    static func relative(epoch: Double?) -> String {
        guard let epoch else { return "—" }
        return relative(Date(timeIntervalSince1970: epoch))
    }

    // MARK: - Geolocalización

    static func flag(_ code: String?) -> String {
        guard let code, !code.isEmpty else { return "🌐" }
        if code == "--" { return "🏠" }
        if code == "??" || code.count != 2 { return "🌐" }
        var result = ""
        for scalar in code.uppercased().unicodeScalars {
            if let flag = UnicodeScalar(127_397 + scalar.value) {
                result.unicodeScalars.append(flag)
            }
        }
        return result.isEmpty ? "🌐" : result
    }

    static func countryLabel(_ code: String?, _ country: String?) -> String {
        guard let country, !country.isEmpty else { return "Desconocido" }
        return "\(flag(code)) \(country)"
    }
}
