import Foundation

// The dashboard's own JSON (docs/80), decoded as-is. Field names stay
// snake_case so a reader can match them to the server line by line.

public struct Me: Codable, Sendable {
    public let email: String
    public let display_name: String?
    public let role: String
    public let via: String
    public let env: String
}

public struct Change: Codable, Hashable, Sendable {
    @Flex public var amount: Double
    @FlexOpt public var pct: Double?
    public let since: String?
}

public struct Account: Codable, Hashable, Identifiable, Sendable {
    public let id: String
    public let item_id: String?
    public let kind: String?
    public let name: String
    public let official_name: String?
    public let mask: String?
    public let type: String?
    public let subtype: String?
    public let manual_category: String?
    public let iso_currency: String?
    @FlexOpt public var current_balance: Double?
    @FlexOpt public var available_balance: Double?
    @FlexOpt public var credit_limit: Double?
    public let balance_updated_at: String?
    public let is_liability: Bool
    public let is_hidden: Bool?
    public let is_business: Bool?
    public let institution_name: String?
    public let item_status: String?
    public let secured_by_id: String?
    public let change_1m: Change?
    public let trend: [Flex]?
    /// Only in /glance: which overview group the account sits in.
    public let group: String?
    public let group_label: String?

    public var balance: Double { current_balance ?? 0 }
    public var currency: String { iso_currency ?? "USD" }
    public var trendValues: [Double] { (trend ?? []).map(\.wrappedValue) }
    public var isManual: Bool { kind == "manual" }

    /// "Chase ··1234": the institution and the last four, as the web filter says it.
    public var subtitle: String {
        var parts: [String] = []
        if let inst = institution_name, !inst.isEmpty { parts.append(inst) }
        else if isManual { parts.append("Offline") }
        if let m = mask, !m.isEmpty { parts.append("··\(m)") }
        return parts.joined(separator: " ")
    }
}

public struct OverviewGroup: Codable, Hashable, Sendable, Identifiable {
    public let key: String
    public let label: String
    public let is_liability: Bool
    @Flex public var total: Double
    public let change_1m: Change?
    public let accounts: [Account]
    public var id: String { key }
}

public struct Attention: Codable, Hashable, Sendable, Identifiable {
    public let id: String
    public let institution_name: String?
    public let status: String
    public let error_code: String?
}

public struct Overview: Codable, Sendable {
    @Flex public var net_worth: Double
    @Flex public var assets: Double
    @Flex public var liabilities: Double
    public let change_1m: Change?
    public let groups: [OverviewGroup]
    public let as_of: String?
    public let account_count: Int?
    public let items_needing_attention: [Attention]?
}

public struct NetWorthPoint: Codable, Hashable, Sendable {
    public let date: String
    @Flex public var assets: Double
    @Flex public var liabilities: Double
    @Flex public var net: Double
}

public struct NetWorthHistory: Codable, Sendable {
    public let points: [NetWorthPoint]
    public let estimated_before: String?
}

public struct BalancePoint: Codable, Hashable, Sendable {
    public let date: String
    @Flex public var balance: Double
    public let source: String?
}

public struct AccountHistory: Codable, Sendable {
    public let points: [BalancePoint]
}

public struct AccountsList: Codable, Sendable {
    public let accounts: [Account]
}

// MARK: - transactions

public struct Txn: Codable, Hashable, Identifiable, Sendable {
    public let id: String
    public let account_id: String
    public let account_name: String?
    public let account_mask: String?
    public let institution_name: String?
    public let date: String
    public let authorized_date: String?
    /// Plaid's sign: positive is money leaving the account.
    @Flex public var amount: Double
    public let iso_currency: String?
    public let name: String
    public let merchant_name: String?
    public let logo_url: String?
    public let pending: Bool
    public let category_primary: String?
    public let category_detailed: String?
    /// What the dashboard shows: PAYMENT for a card or loan payment, else the
    /// person's own category, else the bank's.
    public let category: String?
    public let user_category: String?
    public let payment_channel: String?
    public let notes: String?

    public var title: String { merchant_name?.isEmpty == false ? merchant_name! : name }
    public var currency: String { iso_currency ?? "USD" }
    public var isInflow: Bool { amount < 0 }
}

public struct TxnPage: Codable, Sendable {
    public let page: Int
    public let page_size: Int
    public let total: Int
    public let transactions: [Txn]
}

public struct CategoriesList: Codable, Sendable {
    public let categories: [String]
}

// MARK: - investments and debts

public struct Holding: Codable, Hashable, Identifiable, Sendable {
    public let id: String
    public let ticker: String?
    public let name: String?
    public let type: String?
    @Flex public var quantity: Double
    @FlexOpt public var cost_basis: Double?
    @FlexOpt public var price: Double?
    @Flex public var value: Double
    public let iso_currency: String?
}

public struct HoldingsAccount: Codable, Sendable, Identifiable {
    public let account: Account
    @Flex public var holdings_value: Double
    public let holdings: [Holding]
    public var id: String { account.id }
}

public struct Holdings: Codable, Sendable {
    @Flex public var total_value: Double
    public let accounts: [HoldingsAccount]
}

public struct LiabilityDetail: Codable, Hashable, Sendable {
    public let kind: String?
    @FlexOpt public var interest_rate_pct: Double?
    public let interest_rate_type: String?
    public let next_payment_due_date: String?
    @FlexOpt public var minimum_payment: Double?
    @FlexOpt public var next_payment_amount: Double?
    @FlexOpt public var last_payment_amount: Double?
    public let last_payment_date: String?
    @FlexOpt public var last_statement_balance: Double?
    public let last_statement_date: String?
    public let is_overdue: Bool?
    public let origination_date: String?
    @FlexOpt public var origination_principal: Double?
    public let loan_term: String?
    public let maturity_date: String?
}

public struct LiabilityAccount: Codable, Sendable, Identifiable {
    public let account: Account
    public let detail: LiabilityDetail?
    public var id: String { account.id }
}

public struct Liabilities: Codable, Sendable {
    @Flex public var total_owed: Double
    public let accounts: [LiabilityAccount]
}

public struct PerformancePoint: Codable, Hashable, Sendable {
    public let date: String
    @Flex public var value: Double
    @Flex public var flows: Double
    @Flex public var `return`: Double
}

public struct BenchmarkPoint: Codable, Hashable, Sendable {
    public let date: String
    @Flex public var `return`: Double
}

public struct BenchmarkLine: Codable, Hashable, Sendable, Identifiable {
    public let key: String
    public let label: String
    public let source: String?
    public let points: [BenchmarkPoint]
    public var id: String { key }
}

public struct BenchmarkOption: Codable, Hashable, Sendable, Identifiable {
    public let key: String
    public let label: String
    public let available: Bool
    public let since: String?
    public let note: String?
    public var id: String { key }
}

public struct PerformanceAccount: Codable, Hashable, Sendable {
    public let id: String
    public let name: String
    public let rebuilt: Bool?
    @FlexOpt public var coverage: Double?
    public let tracked_since: String?
}

public struct Performance: Codable, Sendable {
    public let from: String
    public let to: String
    public let estimated_before: String?
    public let series: [PerformancePoint]
    public let accounts: [PerformanceAccount]
    public let benchmarks: [BenchmarkLine]
    public let available: [BenchmarkOption]
}
