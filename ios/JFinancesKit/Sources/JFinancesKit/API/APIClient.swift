import Foundation

public enum APIError: Error, LocalizedError, Sendable, Equatable {
    /// No credential on this phone: show the sign-in screen.
    case notLinked
    /// 401/403 with an `auth.*` code: the token was refused.
    case unauthorized(code: String, message: String)
    case http(status: Int, code: String?, message: String)
    case transport(String)
    case decoding(String)

    /// The token itself is finished (revoked, unknown, or its person was
    /// removed): throw it away and sign in again.
    public var tokenIsDead: Bool {
        if case .unauthorized(let code, _) = self {
            return code == "auth.bad_token" || code == "auth.missing_credential" || code == "auth.not_allowed"
        }
        return false
    }

    public var errorDescription: String? {
        switch self {
        case .notLinked: return "This phone isn't signed in."
        case .unauthorized(let code, let message):
            switch code {
            case "auth.bad_token": return "This phone was unlinked. Sign in again."
            case "auth.not_allowed": return "This account is no longer allowed in."
            case "auth.read_only": return "This phone can look, not change."
            default: return message
            }
        case .http(let status, _, let message): return "\(message) (HTTP \(status))"
        case .transport(let s): return "Couldn't reach jfinances. \(s)"
        case .decoding: return "jfinances answered in a shape this version of the app doesn't understand."
        }
    }
}

/// The Insights slice (docs/80 "Insights"): a date range and whose accounts.
public struct Slice: Hashable, Sendable {
    public var from: String
    public var to: String
    /// personal | business | all
    public var scope: String

    public init(from: String, to: String, scope: String = "personal") {
        self.from = from
        self.to = to
        self.scope = scope
    }

    var query: [URLQueryItem] {
        [URLQueryItem(name: "from", value: from), URLQueryItem(name: "to", value: to),
         URLQueryItem(name: "scope", value: scope)]
    }
}

public struct TxnQuery: Hashable, Sendable {
    public var q: String = ""
    public var accountId: String?
    public var category: String?
    public var from: String?
    public var to: String?
    public var page = 1
    public var pageSize = 50

    public init(q: String = "", accountId: String? = nil, category: String? = nil, from: String? = nil,
                to: String? = nil, page: Int = 1, pageSize: Int = 50) {
        self.q = q
        self.accountId = accountId
        self.category = category
        self.from = from
        self.to = to
        self.page = page
        self.pageSize = pageSize
    }

    var items: [URLQueryItem] {
        var out = [URLQueryItem(name: "page", value: String(page)), URLQueryItem(name: "page_size", value: String(pageSize))]
        let trimmed = q.trimmingCharacters(in: .whitespacesAndNewlines)
        if !trimmed.isEmpty { out.append(URLQueryItem(name: "q", value: trimmed)) }
        if let accountId { out.append(URLQueryItem(name: "account_id", value: accountId)) }
        if let category { out.append(URLQueryItem(name: "category", value: category)) }
        if let from { out.append(URLQueryItem(name: "from", value: from)) }
        if let to { out.append(URLQueryItem(name: "to", value: to)) }
        return out
    }
}

/// Everything the phone reads, with its own token, on the API hostname.
///
/// These are the dashboard's own endpoints, so the app decodes exactly what
/// the web decodes. Only `/mobile/redeem` and `/mobile/unlink` are the
/// phone's own. Every request is a GET except those two: the server refuses
/// anything else from a phone (docs/40 §5).
public final class APIClient: Sendable {
    public static let shared = APIClient()

    private let session: URLSession

    public init(timeout: TimeInterval = 20) {
        let cfg = URLSessionConfiguration.default
        cfg.timeoutIntervalForRequest = timeout
        cfg.waitsForConnectivity = false
        cfg.urlCache = nil
        cfg.requestCachePolicy = .reloadIgnoringLocalCacheData
        session = URLSession(configuration: cfg)
    }

    // MARK: - reads

    public func get<T: Decodable>(_ path: String, _ query: [URLQueryItem] = []) async throws -> T {
        guard let cred = Keychain.read() else { throw APIError.notLinked }
        var req = URLRequest(url: url(cred.server.api, path, query))
        req.setValue("Bearer \(cred.token)", forHTTPHeaderField: "Authorization")
        return try await send(req)
    }

    public func me() async throws -> Me { try await get("/api/v1/me") }
    public func glance() async throws -> Glance { try await get("/api/v1/glance") }
    public func overview() async throws -> Overview { try await get("/api/v1/overview") }

    public func netWorthHistory(range: String) async throws -> NetWorthHistory {
        try await get("/api/v1/networth/history", [URLQueryItem(name: "range", value: range)])
    }

    public func accounts() async throws -> [Account] {
        let list: AccountsList = try await get("/api/v1/accounts")
        return list.accounts
    }

    public func accountHistory(id: String, range: String) async throws -> [BalancePoint] {
        let h: AccountHistory = try await get("/api/v1/accounts/\(id)/history", [URLQueryItem(name: "range", value: range)])
        return h.points
    }

    public func transactions(_ q: TxnQuery) async throws -> TxnPage {
        try await get("/api/v1/transactions", q.items)
    }

    public func categories() async throws -> [String] {
        let c: CategoriesList = try await get("/api/v1/transactions/categories")
        return c.categories
    }

    public func holdings() async throws -> Holdings { try await get("/api/v1/holdings") }
    public func liabilities() async throws -> Liabilities { try await get("/api/v1/liabilities") }

    public func performance(range: String, accountId: String? = nil, benchmarks: [String]) async throws -> Performance {
        var q = [URLQueryItem(name: "range", value: range)]
        if let accountId { q.append(URLQueryItem(name: "account_id", value: accountId)) }
        if !benchmarks.isEmpty { q.append(URLQueryItem(name: "benchmark", value: benchmarks.joined(separator: ","))) }
        return try await get("/api/v1/investments/performance", q)
    }

    public func cashflow(_ slice: Slice, grain: String = "month") async throws -> Cashflow {
        try await get("/api/v1/insights/cashflow", slice.query + [URLQueryItem(name: "grain", value: grain)])
    }

    public func spending(_ slice: Slice, grain: String = "month", category: String? = nil, top: Int = 6) async throws -> Spending {
        var q = slice.query + [URLQueryItem(name: "grain", value: grain), URLQueryItem(name: "top", value: String(top))]
        if let category { q.append(URLQueryItem(name: "category", value: category)) }
        return try await get("/api/v1/insights/spending", q)
    }

    public func merchants(_ slice: Slice, category: String? = nil, top: Int = 25) async throws -> [Merchant] {
        var q = slice.query + [URLQueryItem(name: "top", value: String(top))]
        if let category { q.append(URLQueryItem(name: "category", value: category)) }
        let m: Merchants = try await get("/api/v1/insights/merchants", q)
        return m.merchants
    }

    public func netWorthByClass(range: String) async throws -> NetWorthByClass {
        try await get("/api/v1/insights/networth", [URLQueryItem(name: "range", value: range)])
    }

    public func homes() async throws -> [Home] {
        let h: Homes = try await get("/api/v1/insights/homes")
        return h.homes
    }

    public func loans(extra: Double = 0) async throws -> [LoanPayoff] {
        let q = extra > 0 ? [URLQueryItem(name: "extra", value: String(format: "%.2f", extra))] : []
        let l: Loans = try await get("/api/v1/insights/loans", q)
        return l.loans
    }

    public func cards(range: String) async throws -> CardsInsight {
        try await get("/api/v1/insights/cards", [URLQueryItem(name: "range", value: range)])
    }

    public func recurring() async throws -> RecurringList { try await get("/api/v1/recurring") }

    public func upcoming(days: Int = 30) async throws -> Upcoming {
        try await get("/api/v1/recurring/upcoming", [URLQueryItem(name: "days", value: String(days))])
    }

    public func alerts(days: Int = 60) async throws -> [MoneyAlert] {
        let a: AlertsList = try await get("/api/v1/alerts", [URLQueryItem(name: "days", value: String(days))])
        return a.alerts
    }

    // MARK: - linking, and its undoing

    private struct RedeemBody: Encodable { let code: String; let nonce: String; let name: String }

    /// No bearer: the one-time code is the credential.
    public func redeem(server: Server, code: String, nonce: String, name: String) async throws -> RedeemResponse {
        var req = URLRequest(url: url(server.api, "/api/v1/mobile/redeem", []))
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try JSON.encoder.encode(RedeemBody(code: code, nonce: nonce, name: name))
        return try await send(req)
    }

    /// Revokes the token this phone holds. The caller clears the Keychain
    /// whatever the answer: a token the server no longer honours is worthless.
    public func unlink() async throws {
        guard let cred = Keychain.read() else { return }
        var req = URLRequest(url: url(cred.server.api, "/api/v1/mobile/unlink", []))
        req.httpMethod = "POST"
        req.setValue("Bearer \(cred.token)", forHTTPHeaderField: "Authorization")
        let _: [String: JSONValue] = try await send(req)
    }

    // MARK: - plumbing

    private func url(_ base: URL, _ path: String, _ query: [URLQueryItem]) -> URL {
        var comps = URLComponents(url: base.appendingPathComponent(path), resolvingAgainstBaseURL: false)!
        if !query.isEmpty { comps.queryItems = query }
        return comps.url!
    }

    private struct ErrorBody: Decodable {
        struct Inner: Decodable { let code: String?; let message: String? }
        let error: Inner?
    }

    private func send<T: Decodable>(_ request: URLRequest) async throws -> T {
        var req = request
        req.setValue("application/json", forHTTPHeaderField: "Accept")
        req.setValue("jfinances-iOS", forHTTPHeaderField: "User-Agent")
        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await session.data(for: req)
        } catch {
            throw APIError.transport(error.localizedDescription)
        }
        guard let http = response as? HTTPURLResponse else { throw APIError.transport("no response") }
        guard (200..<300).contains(http.statusCode) else {
            let body = try? JSON.decoder.decode(ErrorBody.self, from: data)
            let code = body?.error?.code
            let message = body?.error?.message ?? HTTPURLResponse.localizedString(forStatusCode: http.statusCode)
            if (http.statusCode == 401 || http.statusCode == 403), let code, code.hasPrefix("auth.") {
                throw APIError.unauthorized(code: code, message: message)
            }
            throw APIError.http(status: http.statusCode, code: code, message: message)
        }
        do {
            return try JSON.decoder.decode(T.self, from: data)
        } catch {
            throw APIError.decoding(String(describing: error))
        }
    }
}
