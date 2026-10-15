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
    /// Where the account counts (Accounts, Overview, net worth by kind): the
    /// server's say, the person's "Counts as" included.
    public let group: String?
    /// Set when the person chose the group (it differs from what the type says).
    public let group_override: String?
    /// Only in /glance: the group's label.
    public let group_label: String?
    /// An offline home's "City, ST 07042" (GET /accounts).
    public let asset_place: String?

    public var balance: Double { current_balance ?? 0 }
    public var currency: String { iso_currency ?? "USD" }
    public var trendValues: [Double] { (trend ?? []).map(\.wrappedValue) }
    public var isManual: Bool { kind == "manual" }

    /// The group, else what the type (or offline category) says, as the web's groupOf.
    public var groupKey: String {
        if let group, !group.isEmpty { return group }
        if isManual {
            switch manual_category {
            case "real_estate": return "real_estate"
            case "vehicle": return "vehicles"
            case "cash": return "cash"
            case "other_liability": return "other_liabilities"
            default: return "other_assets"
            }
        }
        switch type {
        case "depository": return "cash"
        case "credit": return "credit_cards"
        case "investment", "brokerage": return "investments"
        case "loan": return "loans"
        default: return is_liability ? "other_liabilities" : "other_assets"
        }
    }

    /// Homes and cars hold no transactions; every other account can, an offline
    /// one through imported statements.
    public var holdsTransactions: Bool { !(isManual && (groupKey == "real_estate" || groupKey == "vehicles")) }
    public var countsAsInvestment: Bool { groupKey == "investments" }
    public var countsAsCard: Bool { groupKey == "credit_cards" }
    /// An offline home or car: valued from market data once a month.
    public var isValuedAsset: Bool { isManual && (manual_category == "real_estate" || manual_category == "vehicle") }

    /// "Chase: Sapphire ··1234 · business", as the web's account filter says it.
    public var filterLabel: String {
        var out = (institution_name.map { $0 + ": " } ?? "") + Account.nameWithoutMask(name, mask)
        if let m = mask, !m.isEmpty { out += " ··\(m)" }
        if is_business == true { out += " · business" }
        return out
    }

    /// The name without a trailing copy of the mask ("Brokerage - ****3184"): it is shown once, apart.
    public static func nameWithoutMask(_ name: String, _ mask: String?) -> String {
        guard let mask, !mask.isEmpty,
              let r = name.range(of: #"[\s-]*\*+(\w+)\s*$"#, options: .regularExpression) else { return name }
        let tail = name[r].filter { $0.isLetter || $0.isNumber }
        return String(tail) == mask ? String(name[..<r.lowerBound]) : name
    }

    /// The overview's group labels and order (services/networth.py GROUPS).
    public static let groupOrder = ["cash", "investments", "real_estate", "vehicles", "other_assets",
                                    "credit_cards", "loans", "other_liabilities"]
    public static let groupLabels = ["cash": "Cash", "investments": "Investments", "real_estate": "Real estate",
                                     "vehicles": "Vehicles", "other_assets": "Other assets", "credit_cards": "Credit cards",
                                     "loans": "Loans", "other_liabilities": "Other liabilities"]

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
    /// Business by its own flag, else its account's.
    public let is_business: Bool?
    /// The person's say on this one: true business, false personal, nil as its account.
    public let business: Bool?
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
    /// Every matching row's amount added up, Plaid's sign (positive = net money out).
    @Flex public var sum: Double
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

// MARK: - account details (GET /accounts/{id}/details)

/// One fact in an account's details: the bank's, entered by the person, or
/// worked out from the others (`source`), with the format to show it in.
public struct DetailFact: Codable, Hashable, Sendable, Identifiable {
    public let key: String
    public let label: String
    public let value: JSONValue?
    /// money | money0 | pct | ratio | date | months | day | count | text | bool
    public let format: String
    /// bank | you | calc
    public let source: String?
    public let note: String?
    /// The entered field behind this fact: a missing value can be added there (on the dashboard).
    public let field: String?
    public var id: String { key }

    public var isKnown: Bool {
        switch value { case .none, .some(.null): return false; default: return true }
    }
}

public struct DetailSection: Codable, Hashable, Sendable, Identifiable {
    public let key: String
    public let title: String
    public let note: String?
    public let facts: [DetailFact]
    public var id: String { key }
}

public struct AccountDetails: Codable, Sendable {
    /// mortgage | student | loan | credit | depository | investment | asset | other
    public let kind: String
    public let sections: [DetailSection]

    /// Facts the bank doesn't report and nothing could work out, which can be entered.
    public var missing: Int { sections.flatMap(\.facts).filter { !$0.isKnown && $0.field != nil }.count }
}

// MARK: - market values (GET /accounts/{id}/asset)

public struct AssetValuation: Codable, Hashable, Sendable {
    public let month: String
    public let as_of: String
    /// pending | ok | no_value | error | skipped
    public let status: String
    @FlexOpt public var value: Double?
    @FlexOpt public var low: Double?
    @FlexOpt public var high: Double?
    public let inputs: [String: JSONValue]?
    public let detail: [String: JSONValue]?
    public let error: String?
}

public struct AssetDetailsInfo: Codable, Hashable, Sendable {
    public let address_line: String?
    public let city: String?
    public let state: String?
    public let zip: String?
    public let vin: String?
    @FlexOpt public var mileage: Double?
    @FlexOpt public var miles_per_month: Double?
    public let mileage_as_of: String?
    public let vehicle_label: String?
    public let garage_account_id: String?
}

public struct AssetInfo: Codable, Sendable {
    /// home | vehicle, or nil for anything else.
    public let kind: String?
    /// What a valuation still needs: address, city, state, zip; vin, mileage, location.
    public let missing: [String]
    /// The month the next value is asked for (the first of it).
    public let next_month: String?
    public let valuations: [AssetValuation]
    public let valuation_enabled: Bool?
    public let details: AssetDetailsInfo?
    @FlexOpt public var projected_miles: Double?
    public let priced_at_zip: String?
}
