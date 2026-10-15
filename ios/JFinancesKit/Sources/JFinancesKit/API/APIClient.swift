import Foundation

public enum APIError: Error, LocalizedError, Sendable, Equatable {
    /// No credential on this phone: show the sign-in screen.
    case notLinked
    /// 401/403 with an `auth.*` code: the token was refused.
    case unauthorized(code: String, message: String)
    case http(status: Int, code: String?, message: String)
    case transport(String)
    case decoding(String)
    /// 409 from the duplicate guard on a bank link (docs/80 "POST /link/exchange"):
    /// `confirm` is the answer that lets it through, or nil when nothing does.
    case linkGuard(code: String, message: String, institution: String?, accounts: [String], confirm: String?)

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
            case "auth.forbidden": return "That's done on the dashboard, not from a phone."
            default: return message
            }
        case .http(_, _, let message): return message
        case .transport(let s): return "Couldn't reach jFinances. \(s)"
        case .decoding: return "jFinances answered in a shape this version of the app doesn't understand."
        case .linkGuard(_, let message, _, _, _): return message
        }
    }
}

/// The body of a write, as JSON. `null` is sent for a key whose value is
/// nil (it clears), so leave a key out to keep its value.
public struct JSONBody: Encodable, Sendable {
    public var fields: [String: JSONValue]
    public init(_ fields: [String: JSONValue] = [:]) { self.fields = fields }

    public subscript(key: String) -> JSONValue? {
        get { fields[key] }
        set { fields[key] = newValue }
    }

    public func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: Key.self)
        for (k, v) in fields { try c.encode(v, forKey: Key(k)) }
    }

    private struct Key: CodingKey {
        let stringValue: String
        var intValue: Int? { nil }
        init(_ s: String) { stringValue = s }
        init?(stringValue: String) { self.stringValue = stringValue }
        init?(intValue: Int) { nil }
    }
}

public extension JSONValue {
    /// A string, or null when blank.
    static func text(_ s: String?) -> JSONValue {
        guard let s = s?.trimmingCharacters(in: .whitespacesAndNewlines), !s.isEmpty else { return .null }
        return .string(s)
    }

    /// A number, or null when nil.
    static func num(_ d: Double?) -> JSONValue { d.map { .number($0) } ?? .null }

    /// A bool, or null when nil.
    static func flag(_ b: Bool?) -> JSONValue { b.map { .bool($0) } ?? .null }

    /// "1234.56": what a money field sends (the server stores numeric, not float).
    static func money(_ d: Double) -> JSONValue { .string(String(format: "%.2f", d)) }
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

/// How Insights grouped a number, so the transactions behind it add up to it
/// (docs/80 "GET /transactions": `flow` applies Insights' rules, the rest its
/// groupings). The web's lib/drill.ts says the same in its links.
public struct Drill: Hashable, Sendable {
    /// income | spending | all
    public var flow: String
    public var category: String?
    /// A detailed category (or the category, when the bank gave none).
    public var detailed: String?
    /// Insights' merchant name.
    public var merchant: String?
    /// paychecks, dividends, interest, retirement, tax refunds, unemployment, other income.
    public var incomeKind: String?
    /// in | out
    public var direction: String?
    public var notCategory: [String] = []
    public var notDetailed: [String] = []
    /// "kind:merchant" income sources to leave out.
    public var notSource: [String] = []
    /// 0 = Monday.
    public var weekday: Int?
    public var day: Int?
    /// The dates, when not the whole slice (a period of a chart).
    public var from: String?
    public var to: String?
    /// List the biggest amounts first.
    public var largestFirst = false
    /// Why the list was opened, when its numbers need saying ("savings").
    public var why: String?

    public init(flow: String, category: String? = nil, detailed: String? = nil, merchant: String? = nil,
                incomeKind: String? = nil, direction: String? = nil, notCategory: [String] = [],
                notDetailed: [String] = [], notSource: [String] = [], weekday: Int? = nil, day: Int? = nil,
                from: String? = nil, to: String? = nil, largestFirst: Bool = false, why: String? = nil) {
        self.flow = flow
        self.category = category
        self.detailed = detailed
        self.merchant = merchant
        self.incomeKind = incomeKind
        self.direction = direction
        self.notCategory = notCategory
        self.notDetailed = notDetailed
        self.notSource = notSource
        self.weekday = weekday
        self.day = day
        self.from = from
        self.to = to
        self.largestFirst = largestFirst
        self.why = why
    }
}

public struct TxnQuery: Hashable, Sendable {
    public var q: String = ""
    public var accountId: String?
    public var category: String?
    public var from: String?
    public var to: String?
    /// newest (default) or largest: biggest amounts first, either way.
    public var sort = "newest"
    /// Insights' rules and grouping (flow, scope and the rest), when the list is a number's.
    public var drill: Drill?
    /// personal | business | all, with a drill.
    public var scope: String?
    public var page = 1
    public var pageSize = 50

    public init(q: String = "", accountId: String? = nil, category: String? = nil, from: String? = nil,
                to: String? = nil, sort: String = "newest", drill: Drill? = nil, scope: String? = nil,
                page: Int = 1, pageSize: Int = 50) {
        self.q = q
        self.accountId = accountId
        self.category = category
        self.from = from
        self.to = to
        self.sort = sort
        self.drill = drill
        self.scope = scope
        self.page = page
        self.pageSize = pageSize
    }

    var items: [URLQueryItem] {
        var out = [URLQueryItem(name: "page", value: String(page)), URLQueryItem(name: "page_size", value: String(pageSize))]
        func add(_ name: String, _ value: String?) { if let value, !value.isEmpty { out.append(URLQueryItem(name: name, value: value)) } }
        add("q", q.trimmingCharacters(in: .whitespacesAndNewlines))
        add("account_id", accountId)
        add("category", category ?? drill?.category)
        add("from", drill?.from ?? from)
        add("to", drill?.to ?? to)
        if sort != "newest" { add("sort", sort) }
        if let d = drill {
            add("flow", d.flow)
            add("scope", scope)
            add("detailed", d.detailed)
            add("merchant", d.merchant)
            add("income_kind", d.incomeKind)
            add("direction", d.direction)
            for v in d.notCategory { add("not_category", v) }
            for v in d.notDetailed { add("not_detailed", v) }
            for v in d.notSource { add("not_source", v) }
            add("weekday", d.weekday.map(String.init))
            add("day", d.day.map(String.init))
        }
        return out
    }
}

/// Everything the phone reads and changes, with its own token, on the API
/// hostname.
///
/// These are the dashboard's own endpoints, so the app sends and decodes
/// exactly what the web does. Only `/mobile/redeem` and `/mobile/unlink` are
/// the phone's own. A phone edits as the dashboard does; managing phones is
/// the dashboard's alone (docs/40 §5).
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

    /// Everything known about one account: the bank's facts, what was entered
    /// where the bank is silent, and what follows from both.
    public func accountDetails(id: String) async throws -> AccountDetails {
        try await get("/api/v1/accounts/\(id)/details")
    }

    /// An offline home's or car's valuation inputs and its monthly market values.
    public func asset(id: String) async throws -> AssetInfo {
        try await get("/api/v1/accounts/\(id)/asset")
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

    public func items() async throws -> [Item] {
        let list: ItemsList = try await get("/api/v1/items")
        return list.items
    }

    // MARK: - writes (docs/80)

    /// A write with the phone's token. `body` nil sends no body (a bare POST).
    public func send<T: Decodable>(_ method: String, _ path: String, body: JSONBody? = nil) async throws -> T {
        guard let cred = Keychain.read() else { throw APIError.notLinked }
        var req = URLRequest(url: url(cred.server.api, path, []))
        req.httpMethod = method
        req.setValue("Bearer \(cred.token)", forHTTPHeaderField: "Authorization")
        if let body {
            req.setValue("application/json", forHTTPHeaderField: "Content-Type")
            req.httpBody = try JSON.encoder.encode(body)
        }
        return try await send(req)
    }

    /// A write whose answer is nothing (204) or nothing worth decoding.
    public func act(_ method: String, _ path: String, body: JSONBody? = nil) async throws {
        let _: Nothing = try await send(method, path, body: body)
    }

    /// Category (nil keeps it; `.null` goes back to the bank's), note, business.
    public func patchTransaction(id: String, _ body: JSONBody) async throws -> Txn {
        try await send("PATCH", "/api/v1/transactions/\(id)", body: body)
    }

    /// Name, hidden, business, where it counts (`group`), what secures it (`secured_by_id`).
    public func patchAccount(id: String, _ body: JSONBody) async throws -> Account {
        try await send("PATCH", "/api/v1/accounts/\(id)", body: body)
    }

    /// The latest balances the bank has for this account's connection (free, rate limited).
    public func refreshAccount(id: String) async throws -> Account {
        try await send("POST", "/api/v1/accounts/\(id)/refresh")
    }

    /// An offline account's value, as of a day (today when nil).
    public func setValue(id: String, value: Double, asOf: String?, note: String?) async throws -> Account {
        var b = JSONBody(["value": .money(value)])
        if let asOf, !asOf.isEmpty { b["as_of"] = .string(asOf) }
        if let note, !note.isEmpty { b["note"] = .string(note) }
        return try await send("PUT", "/api/v1/accounts/\(id)/value", body: b)
    }

    public func createManual(_ body: JSONBody) async throws -> Account {
        try await send("POST", "/api/v1/accounts/manual", body: body)
    }

    public func deleteAccount(id: String) async throws {
        try await act("DELETE", "/api/v1/accounts/\(id)")
    }

    /// A home's address or a car's VIN, mileage and where it's kept (docs/80 "PUT /accounts/{id}/asset").
    public func putAsset(id: String, _ body: JSONBody) async throws -> AssetInfo {
        try await send("PUT", "/api/v1/accounts/\(id)/asset", body: body)
    }

    /// What the bank doesn't report, entered; the details as they read with it.
    public func putTerms(id: String, _ body: JSONBody) async throws -> AccountDetails {
        try await send("PUT", "/api/v1/accounts/\(id)/terms", body: body)
    }

    /// The details as they would read with these terms, saving nothing.
    public func previewTerms(id: String, _ body: JSONBody) async throws -> AccountDetails {
        try await send("POST", "/api/v1/accounts/\(id)/terms/preview", body: body)
    }

    /// A subscription's verdict (detected | confirmed | dismissed) and name.
    public func patchRecurring(id: String, _ body: JSONBody) async throws -> RecurringStream {
        try await send("PATCH", "/api/v1/recurring/\(id)", body: body)
    }

    public func detectRecurring() async throws -> Int {
        struct Found: Decodable { let found: Int }
        let f: Found = try await send("POST", "/api/v1/recurring/detect")
        return f.found
    }

    public func dismissAlert(key: String) async throws {
        try await act("POST", "/api/v1/alerts/dismiss", body: JSONBody(["key": .string(key)]))
    }

    public func dismissAllAlerts() async throws -> Int {
        struct Dismissed: Decodable { let dismissed: Int }
        let d: Dismissed = try await send("POST", "/api/v1/alerts/dismiss-all")
        return d.dismissed
    }

    /// Queue a sync (transactions, investments, liabilities) for one connection.
    public func syncItem(id: String) async throws -> Bool {
        struct R: Decodable { let queued: Bool }
        let r: R = try await send("POST", "/api/v1/items/\(id)/sync")
        return r.queued
    }

    public func syncAll() async throws {
        try await act("POST", "/api/v1/sync/all")
    }

    public func refreshPrices() async throws -> Bool {
        let q: Queued = try await send("POST", "/api/v1/prices/refresh")
        return q.queued
    }

    /// `/item/remove` at the bank's aggregator: the connection stops and stops billing; history stays.
    public func removeItem(id: String) async throws -> Item {
        try await send("DELETE", "/api/v1/items/\(id)")
    }

    // MARK: - connecting a bank (docs/30 "Link on the phones")

    /// A link token to connect something new (`kind`: banking | investments).
    public func linkToken(kind: String) async throws -> LinkToken {
        try await send("POST", "/api/v1/link/token", body: JSONBody(["kind": .string(kind), "platform": .string("ios")]))
    }

    /// A link token in update mode: re-link, or add accounts to, one connection.
    public func relinkToken(itemId: String) async throws -> LinkToken {
        try await send("POST", "/api/v1/items/\(itemId)/relink", body: JSONBody(["platform": .string("ios")]))
    }

    /// Trade Link's public token for a connection. A 409 from the duplicate
    /// guard surfaces as `APIError.linkGuard`; answer it with `confirm`.
    public func linkExchange(publicToken: String, metadata: JSONValue?, sessionId: String, confirm: String?) async throws -> Item {
        var b = JSONBody(["public_token": .string(publicToken), "link_session_id": .string(sessionId)])
        if let metadata { b["metadata"] = metadata }
        if let confirm { b["confirm"] = .string(confirm) }
        return try await send("POST", "/api/v1/link/exchange", body: b)
    }

    /// After update-mode Link finishes: the connection is well again, a sync is queued.
    public func linkUpdateComplete(sessionId: String) async throws -> Item {
        try await send("POST", "/api/v1/link/update-complete", body: JSONBody(["link_session_id": .string(sessionId)]))
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
        struct Inner: Decodable {
            let code: String?
            let message: String?
            // The duplicate guard's extras (409 link.*).
            let institution: String?
            let accounts: [String]?
            let confirm: String?
        }
        let error: Inner?
    }

    /// Decodes anything, for a 204 or an answer nobody reads.
    private struct Nothing: Decodable {
        init() {}
        init(from decoder: Decoder) throws {}
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
            if http.statusCode == 409, let code, code.hasPrefix("link."), let inner = body?.error {
                throw APIError.linkGuard(code: code, message: message, institution: inner.institution,
                                         accounts: inner.accounts ?? [], confirm: inner.confirm)
            }
            if http.statusCode == 422 {
                // The server's validation detail is for programmers; say what the person can act on.
                throw APIError.http(status: 422, code: code, message: "Something in the form isn't valid. Check the values and try again.")
            }
            throw APIError.http(status: http.statusCode, code: code, message: message)
        }
        if T.self == Nothing.self, let empty = Nothing() as? T { return empty }
        do {
            return try JSON.decoder.decode(T.self, from: data)
        } catch {
            throw APIError.decoding(String(describing: error))
        }
    }
}
