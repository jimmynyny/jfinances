import JFinancesKit
import SwiftUI
import WidgetKit

@main
struct JFinancesWidgets: WidgetBundle {
    init() { JFFont.register() }

    var body: some Widget {
        NetWorthWidget()
        MonthWidget()
        UpcomingWidget()
        AccountWidget()
        AccountsWidget()
    }
}

struct NetWorthWidget: Widget {
    var body: some WidgetConfiguration {
        AppIntentConfiguration(kind: "NetWorthWidget", intent: NetWorthIntent.self, provider: GlanceProvider<NetWorthIntent>()) { e in
            NetWorthView(entry: e).widgetURL(URL(string: "jfinances://overview"))
        }
        .configurationDisplayName("Net worth")
        .description("Net worth, its 30-day change and line.")
        .supportedFamilies([.systemSmall, .systemMedium, .accessoryRectangular, .accessoryInline, .accessoryCircular])
    }
}

struct MonthWidget: Widget {
    var body: some WidgetConfiguration {
        AppIntentConfiguration(kind: "MonthWidget", intent: MonthIntent.self, provider: GlanceProvider<MonthIntent>()) { e in
            MonthView(entry: e).widgetURL(URL(string: "jfinances://insights/cashflow"))
        }
        .configurationDisplayName("This month")
        .description("Money in and out this month, and where it went.")
        .supportedFamilies([.systemSmall, .systemMedium, .systemLarge, .accessoryRectangular])
    }
}

struct UpcomingWidget: Widget {
    var body: some WidgetConfiguration {
        AppIntentConfiguration(kind: "UpcomingWidget", intent: UpcomingIntent.self, provider: GlanceProvider<UpcomingIntent>()) { e in
            UpcomingView(entry: e).widgetURL(URL(string: "jfinances://insights/subscriptions"))
        }
        .configurationDisplayName("Coming up")
        .description("Subscriptions and bills expected in the next two weeks.")
        .supportedFamilies([.systemSmall, .systemMedium, .systemLarge, .accessoryRectangular])
    }
}

struct AccountWidget: Widget {
    var body: some WidgetConfiguration {
        AppIntentConfiguration(kind: "AccountWidget", intent: AccountIntent.self, provider: GlanceProvider<AccountIntent>()) { e in
            AccountView(entry: e)
                .widgetURL(URL(string: e.configuration.account.map { "jfinances://account/\($0.id)" } ?? "jfinances://accounts"))
        }
        .configurationDisplayName("Account")
        .description("One account's balance and trend.")
        .supportedFamilies([.systemSmall, .accessoryRectangular, .accessoryInline, .accessoryCircular])
    }
}

struct AccountsWidget: Widget {
    var body: some WidgetConfiguration {
        AppIntentConfiguration(kind: "AccountsWidget", intent: AccountsIntent.self, provider: GlanceProvider<AccountsIntent>()) { e in
            AccountsView(entry: e).widgetURL(URL(string: "jfinances://accounts"))
        }
        .configurationDisplayName("Accounts")
        .description("Up to four accounts' balances side by side.")
        .supportedFamilies([.systemMedium])
    }
}
