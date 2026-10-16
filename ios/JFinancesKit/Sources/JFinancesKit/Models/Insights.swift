import Foundation

// MARK: - cash flow and spending (GET /insights/*)

public struct CashflowPeriod: Codable, Hashable, Sendable, Identifiable {
    public let period: String
    public let label: String
    @Flex public var income: Double
    @Flex public var spending: Double
    @Flex public var net: Double
    @FlexOpt public var savings_rate: Double?
    public var id: String { period }
}

public struct CashflowTotals: Codable, Hashable, Sendable {
    @Flex public var income: Double
    @Flex public var spending: Double
    @Flex public var net: Double
    @FlexOpt public var savings_rate: Double?
}

public struct CashflowAverages: Codable, Hashable, Sendable {
    @Flex public var income: Double
    @Flex public var spending: Double
    @Flex public var net: Double
    public let periods: Int?
}

public struct IncomeSource: Codable, Hashable, Sendable, Identifiable {
    public let kind: String
    public let label: String
    @Flex public var amount: Double
    public let count: Int?
    public var id: String { kind + label }
}

public struct CategoryAmount: Codable, Hashable, Sendable, Identifiable {
    public let key: String
    @Flex public var amount: Double
    public var id: String { key }
}

public struct Cashflow: Codable, Sendable {
    public let grain: String
    public let periods: [CashflowPeriod]
    public let totals: CashflowTotals
    public let averages: CashflowAverages
    public let income_sources: [IncomeSource]
    public let spending_categories: [CategoryAmount]
}

public struct SpendingSeries: Codable, Hashable, Sendable, Identifiable {
    public let key: String
    @Flex public var total: Double
    public let values: [Flex]
    public var id: String { key }
    public var numbers: [Double] { values.map(\.wrappedValue) }
}

public struct PeriodLabel: Codable, Hashable, Sendable {
    public let period: String
    public let label: String
}

public struct Spending: Codable, Sendable {
    public let grain: String
    public let group: String
    public let category: String?
    public let periods: [PeriodLabel]
    public let series: [SpendingSeries]
    @Flex public var total: Double
}

public struct Merchant: Codable, Hashable, Sendable, Identifiable {
    public let label: String
    @Flex public var total: Double
    public let count: Int
    @Flex public var average: Double
    public let category: String
    public let first_seen: String?
    public let last_seen: String
    public let is_new: Bool
    public let trend: [Flex]
    public var id: String { label }
}

public struct Merchants: Codable, Sendable {
    public let merchants: [Merchant]
}

// MARK: - net worth and debt

public struct ClassGroup: Codable, Hashable, Sendable, Identifiable {
    public let key: String
    public let label: String
    public let liability: Bool
    public var id: String { key }
}

public struct NetWorthByClass: Codable, Sendable {
    public let groups: [ClassGroup]
    /// Month ends; one key per group (debts positive) plus assets/liabilities/net.
    public let points: [[String: JSONValue]]

    public func value(_ point: [String: JSONValue], _ key: String) -> Double { point[key]?.number ?? 0 }
}

public struct HomeLoan: Codable, Hashable, Sendable, Identifiable {
    public let id: String
    public let name: String
    public let mask: String?
    @Flex public var balance: Double
    @FlexOpt public var rate: Double?
}

public struct HomeHistory: Codable, Hashable, Sendable {
    public let date: String
    @Flex public var value: Double
    @Flex public var owed: Double
    @Flex public var equity: Double
}

public struct Home: Codable, Hashable, Sendable, Identifiable {
    public let id: String
    public let name: String
    public let category: String?
    @Flex public var value: Double
    @Flex public var owed: Double
    @Flex public var equity: Double
    @FlexOpt public var ltv: Double?
    public let loans: [HomeLoan]
    public let history: [HomeHistory]
}

public struct Homes: Codable, Sendable { public let homes: [Home] }

public struct YearSplit: Codable, Hashable, Sendable {
    public let year: Int
    @Flex public var interest: Double
    @Flex public var principal: Double
}

public struct LoanSchedule: Codable, Hashable, Sendable {
    @Flex public var payment: Double
    public let payoff: String?
    public let months: Int?
    @FlexOpt public var interest: Double?
    public let per_year: [YearSplit]
}

public struct LoanWhatIf: Codable, Hashable, Sendable {
    @Flex public var extra: Double
    public let payoff: String
    public let months: Int
    @Flex public var interest: Double
    public let months_saved: Int
    @Flex public var interest_saved: Double
}

public struct LoanPayoff: Codable, Hashable, Sendable, Identifiable {
    public let id: String
    public let name: String
    public let kind: String?
    @Flex public var balance: Double
    @FlexOpt public var rate: Double?
    @FlexOpt public var scheduled_payment: Double?
    public let maturity_date: String?
    @FlexOpt public var ytd_interest: Double?
    public let note: String?
    public let schedule: LoanSchedule?
    public let what_if: LoanWhatIf?
}

public struct Loans: Codable, Sendable { public let loans: [LoanPayoff] }

public struct CardHistory: Codable, Hashable, Sendable {
    public let date: String
    @Flex public var balance: Double
    @FlexOpt public var utilization: Double?
}

public struct CardRow: Codable, Hashable, Sendable, Identifiable {
    public let id: String
    public let name: String
    public let mask: String?
    public let institution_name: String?
    public let is_business: Bool?
    @FlexOpt public var limit: Double?
    @Flex public var balance: Double
    @FlexOpt public var utilization: Double?
    public let history: [CardHistory]
}

public struct UtilizationPoint: Codable, Hashable, Sendable {
    public let date: String
    @FlexOpt public var utilization: Double?
}

public struct CardCharges: Codable, Hashable, Sendable {
    public let month: String
    @Flex public var interest: Double
    @Flex public var fees: Double
}

public struct CardTotals: Codable, Hashable, Sendable {
    @Flex public var interest: Double
    @Flex public var fees: Double
}

public struct CardsInsight: Codable, Sendable {
    public let cards: [CardRow]
    public let overall: [UtilizationPoint]
    public let charges: [CardCharges]
    public let totals: CardTotals
}

// MARK: - subscriptions and alerts

public struct RecurringStream: Codable, Hashable, Sendable, Identifiable {
    public let id: String
    public let merchant: String
    public let name: String?
    public let label: String
    public let cadence: String
    @Flex public var amount: Double
    @Flex public var last_amount: Double
    @FlexOpt public var previous_amount: Double?
    public let price_changed_on: String?
    public let first_date: String
    public let last_date: String
    public let next_date: String
    public let charge_count: Int
    public let category: String?
    public let account_name: String?
    public let account_mask: String?
    public let is_business: Bool?
    /// detected | confirmed | dismissed: the person's verdict.
    public let status: String
    /// subscription | recurring (older servers send neither: recurring).
    public let kind: String?
    /// model | user: who sorted it; the user's choice is kept.
    public let kind_source: String?
    /// active | lapsed: whether charges still arrive on time.
    public let state: String
    @Flex public var monthly: Double

    public var isSubscription: Bool { kind == "subscription" }
}

public struct RecurringTotals: Codable, Sendable {
    @Flex public var monthly_confirmed: Double
    @Flex public var monthly_detected: Double
}

public struct RecurringList: Codable, Sendable {
    public let streams: [RecurringStream]
    @Flex public var monthly_confirmed: Double
    @Flex public var monthly_detected: Double
    /// The same per kind: "subscription", "recurring".
    public let kinds: [String: RecurringTotals]?
    /// Whether the server sorts subscriptions (it has a model to ask).
    public let sorting: Bool?
}

public struct UpcomingCharge: Codable, Hashable, Sendable, Identifiable {
    public let stream_id: String
    public let label: String
    public let date: String
    public let overdue: Bool
    @Flex public var amount: Double
    public let cadence: String
    public let status: String
    public let category: String?
    public let account_name: String?
    public let is_business: Bool?
    public var id: String { stream_id + date }
}

public struct Upcoming: Codable, Sendable {
    public let from: String
    public let to: String
    @Flex public var total: Double
    public let count: Int?
    public let items: [UpcomingCharge]
}

public struct MoneyAlert: Codable, Hashable, Sendable, Identifiable {
    public let key: String
    /// price | duplicate | large
    public let kind: String
    public let date: String
    public let merchant: String
    @Flex public var amount: Double
    @FlexOpt public var previous: Double?
    @FlexOpt public var usual: Double?
    public let basis: String?
    public let category: String?
    public var id: String { key }
}

public struct AlertsList: Codable, Sendable {
    public let days: Int?
    public let alerts: [MoneyAlert]
}

// MARK: - the widgets' one read (GET /glance)

public struct GlanceNetWorth: Codable, Sendable {
    @Flex public var net: Double
    @Flex public var assets: Double
    @Flex public var liabilities: Double
    public let change_1m: Change?
    public let as_of: String?
    public let points: [GlanceNetPoint]
}

public struct GlanceNetPoint: Codable, Hashable, Sendable {
    public let date: String
    @Flex public var net: Double
}

public struct GlanceMonth: Codable, Sendable {
    public let from: String
    public let to: String
    @Flex public var income: Double
    @Flex public var spending: Double
    @Flex public var net: Double
    @FlexOpt public var savings_rate: Double?
    public let categories: [CategoryAmount]
}

public struct GlanceGroup: Codable, Hashable, Sendable, Identifiable {
    public let key: String
    public let label: String
    public let is_liability: Bool
    @Flex public var total: Double
    public var id: String { key }
}

public struct GlanceAlerts: Codable, Sendable { public let count: Int }

public struct Glance: Codable, Sendable {
    public let as_of: String
    public let net_worth: GlanceNetWorth
    public let month: GlanceMonth
    public let upcoming: Upcoming
    public let accounts: [Account]
    public let groups: [GlanceGroup]
    public let alerts: GlanceAlerts
    public let attention: [Attention]
}

// MARK: - linking

public struct RedeemResponse: Codable, Sendable {
    public let token: String
    public let id: String
    public let name: String
    public let email: String
    public let display_name: String?
}
