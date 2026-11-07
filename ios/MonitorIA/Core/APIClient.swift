import Foundation

// ============================================================================
// Cliente HTTP/WebSocket del backend Monitor IA.
// La decodificación es tolerante (snake_case → camelCase) y sin fechas ISO.
// ============================================================================

enum APIError: LocalizedError {
    case invalidServerURL
    case invalidResponse
    case http(status: Int, message: String)
    case decoding
    case network(String)

    var errorDescription: String? {
        switch self {
        case .invalidServerURL:
            return "La URL del servidor no es válida. Ejemplo: http://192.168.1.35:8080"
        case .invalidResponse:
            return "El servidor devolvió una respuesta inesperada."
        case .http(let status, let message):
            return "Error HTTP \(status): \(message)"
        case .decoding:
            return "No se pudo interpretar la respuesta del servidor."
        case .network(let message):
            return message
        }
    }
}

struct APIClient {
    let baseURL: URL
    private let session: URLSession
    private let decoder: JSONDecoder
    private let encoder: JSONEncoder

    init?(serverString: String, session: URLSession = .shared) {
        guard let url = Self.normalizeServer(serverString) else { return nil }
        self.baseURL = url
        self.session = session

        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        self.decoder = decoder

        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        self.encoder = encoder
    }

    /// Normaliza lo que escribe el usuario: añade http:// si falta, valida el esquema
    /// y elimina la barra final.
    static func normalizeServer(_ raw: String) -> URL? {
        var value = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !value.isEmpty else { return nil }
        if !value.contains("://") { value = "http://" + value }
        while value.hasSuffix("/") { value.removeLast() }
        guard var components = URLComponents(string: value),
              let scheme = components.scheme?.lowercased(),
              scheme == "http" || scheme == "https",
              components.host != nil else {
            return nil
        }
        components.query = nil
        components.fragment = nil
        return components.url
    }

    func makeURL(path: String, query: [URLQueryItem] = []) -> URL? {
        guard var components = URLComponents(url: baseURL, resolvingAgainstBaseURL: false) else { return nil }
        let basePath = components.path.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        let extraPath = path.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        components.path = "/" + [basePath, extraPath].filter { !$0.isEmpty }.joined(separator: "/")
        components.queryItems = query.isEmpty ? nil : query
        return components.url
    }

    var websocketURL: URL? {
        guard var components = URLComponents(url: baseURL, resolvingAgainstBaseURL: false) else { return nil }
        components.scheme = components.scheme?.lowercased() == "https" ? "wss" : "ws"
        let basePath = components.path.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        components.path = "/" + [basePath, "ws/telemetry"].filter { !$0.isEmpty }.joined(separator: "/")
        components.query = nil
        components.fragment = nil
        return components.url
    }

    // MARK: - GET / PUT / POST

    func get<T: Decodable>(_ path: String, query: [URLQueryItem] = []) async throws -> T {
        guard let url = makeURL(path: path, query: query) else { throw APIError.invalidServerURL }
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        let (data, response) = try await session.data(for: request)
        try Self.validate(response: response, data: data)
        do {
            return try decoder.decode(T.self, from: data)
        } catch {
            throw APIError.decoding
        }
    }

    func send<Response: Decodable, Body: Encodable>(
        _ method: String,
        _ path: String,
        body: Body
    ) async throws -> Response {
        guard let url = makeURL(path: path) else { throw APIError.invalidServerURL }
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.httpBody = try encoder.encode(body)
        let (data, response) = try await session.data(for: request)
        try Self.validate(response: response, data: data)
        do {
            return try decoder.decode(Response.self, from: data)
        } catch {
            throw APIError.decoding
        }
    }

    func postIgnoringResponse(_ path: String) async throws {
        guard let url = makeURL(path: path) else { throw APIError.invalidServerURL }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        let (data, response) = try await session.data(for: request)
        try Self.validate(response: response, data: data)
    }

    func post<Response: Decodable>(_ path: String) async throws -> Response {
        guard let url = makeURL(path: path) else { throw APIError.invalidServerURL }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        let (data, response) = try await session.data(for: request)
        try Self.validate(response: response, data: data)
        do {
            return try decoder.decode(Response.self, from: data)
        } catch {
            throw APIError.decoding
        }
    }

    // MARK: - CSV

    func downloadCSV(range: ChartRange) async throws -> URL {
        guard let url = makeURL(
            path: "/api/export.csv",
            query: [URLQueryItem(name: "range", value: range.rawValue)]
        ) else { throw APIError.invalidServerURL }

        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        let (temporaryURL, response) = try await session.download(for: request)
        guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
            throw APIError.http(
                status: (response as? HTTPURLResponse)?.statusCode ?? -1,
                message: "No se pudo exportar el CSV"
            )
        }
        let destination = FileManager.default.temporaryDirectory
            .appendingPathComponent("monitor-ia-\(range.rawValue)-\(Int(Date().timeIntervalSince1970)).csv")
        try? FileManager.default.removeItem(at: destination)
        try FileManager.default.moveItem(at: temporaryURL, to: destination)
        return destination
    }

    // MARK: - Helpers

    private static func validate(response: URLResponse, data: Data) throws {
        guard let http = response as? HTTPURLResponse else { throw APIError.invalidResponse }
        guard (200..<300).contains(http.statusCode) else {
            let message: String
            if let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
               let detail = json["detail"] as? String {
                message = detail
            } else {
                message = String(data: data, encoding: .utf8) ?? "Error desconocido"
            }
            throw APIError.http(status: http.statusCode, message: message)
        }
    }
}
