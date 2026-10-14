import AppIntents
import JFinancesKit
import WidgetKit

/// Every widget can hide its figures (shown as dots) for a Home Screen in
/// view of others. Lock Screen figures are privacy-sensitive regardless: the
/// system hides them until the phone is unlocked.
protocol AmountsIntent: WidgetConfigurationIntent {
    var showAmounts: Bool { get }
}

struct NetWorthIntent: AmountsIntent {
    static var title: LocalizedStringResource { "Net worth" }
    static var description: IntentDescription { IntentDescription("Net worth, its 30-day change and line.") }

    @Parameter(title: "Show amounts", default: true)
    var showAmounts: Bool
}

struct MonthIntent: AmountsIntent {
    static var title: LocalizedStringResource { "This month" }
    static var description: IntentDescription { IntentDescription("Money in and out this month, and where it went.") }

    @Parameter(title: "Show amounts", default: true)
    var showAmounts: Bool
}

struct UpcomingIntent: AmountsIntent {
    static var title: LocalizedStringResource { "Coming up" }
    static var description: IntentDescription { IntentDescription("Subscriptions and bills expected in the next two weeks.") }

    @Parameter(title: "Show amounts", default: true)
    var showAmounts: Bool
}

/// An account, listed from the last glance so the picker works offline.
struct AccountEntity: AppEntity {
    let id: String
    let name: String
    let subtitle: String

    static var typeDisplayRepresentation: TypeDisplayRepresentation { "Account" }
    static var defaultQuery = AccountQuery()

    var displayRepresentation: DisplayRepresentation {
        DisplayRepresentation(title: "\(name)", subtitle: "\(subtitle)")
    }
}

struct AccountQuery: EntityQuery {
    private func all() async -> [AccountEntity] {
        let (cached, _) = await GlanceCache.fetch(maxAge: 3600)
        return (cached?.glance.accounts ?? []).map { AccountEntity(id: $0.id, name: $0.name, subtitle: $0.subtitle) }
    }

    func entities(for identifiers: [String]) async throws -> [AccountEntity] {
        await all().filter { identifiers.contains($0.id) }
    }

    func suggestedEntities() async throws -> [AccountEntity] { await all() }
}

struct AccountIntent: AmountsIntent {
    static var title: LocalizedStringResource { "Account" }
    static var description: IntentDescription { IntentDescription("One account's balance and trend.") }

    @Parameter(title: "Account")
    var account: AccountEntity?

    @Parameter(title: "Show amounts", default: true)
    var showAmounts: Bool
}
