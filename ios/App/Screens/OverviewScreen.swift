import JFinancesKit
import SwiftUI

/// The household at a glance: net worth and its line, this month's money in
/// and out, what is coming up, alerts, and where the money sits.
struct OverviewScreen: View {
    @Environment(AppModel.self) private var model
    @AppStorage("jf.overview.range") private var range = "6m"

    var body: some View {
        Screen("Overview") {
            if let g = model.glance {
                if !g.attention.isEmpty { AttentionNote(items: g.attention) }
                netWorth(g)
                month(g)
                upcoming(g)
                if g.alerts.count > 0 { alerts }
                groups(g)
                if let at = model.glanceFetchedAt {
                    Fine("updated \(Fmt.relative(ISO8601DateFormatter().string(from: at)))")
                        .frame(maxWidth: .infinity, alignment: .center)
                        .padding(.top, 4)
                }
            } else if let err = model.lastError {
                ErrorNote(err) { Task { await model.refreshGlance(force: true) } }
            } else {
                Skeleton(height: 320)
                Skeleton(height: 160)
            }
        }
    }

    private func netWorth(_ g: Glance) -> some View {
        Panel("net worth", actions: {
            Chips(options: [("1m", "1m"), ("3m", "3m"), ("6m", "6m"), ("1y", "1y"), ("all", "all")], value: $range)
        }) {
            VStack(alignment: .leading, spacing: 14) {
                Readout(value: Fmt.money(g.net_worth.net, cents: false), size: 46,
                        delta: g.net_worth.change_1m.map { AnyView(Delta(amount: $0.amount, pct: $0.pct, label: "30 days")) })
                Loader(id: range, height: 180) {
                    try await APIClient.shared.netWorthHistory(range: range)
                } content: { h in
                    TrendChart(points: h.points.compactMap { p in Fmt.day(p.date).map { DatedValue(date: $0, value: p.net) } },
                               estimatedBefore: Fmt.day(h.estimated_before))
                }
                HStack(spacing: 12) {
                    StatTile("owned") { MoneyText(g.net_worth.assets, cents: false, size: 16, weight: .medium) }
                    StatTile("owed") { MoneyText(g.net_worth.liabilities, cents: false, size: 16, weight: .medium) }
                }
                if g.net_worth.assets > 0 {
                    PixelMeter(ratio: g.net_worth.liabilities / g.net_worth.assets, cells: 40, tone: .ink, height: 6)
                    Fine("owed is \(Fmt.pct(g.net_worth.liabilities / g.net_worth.assets, digits: 0)) of owned")
                }
            }
        }
    }

    private func month(_ g: Glance) -> some View {
        let m = g.month
        let total = m.categories.reduce(0) { $0 + $1.amount }
        return Panel("this month", actions: { Fine("personal") }) {
            VStack(alignment: .leading, spacing: 14) {
                HStack(spacing: 12) {
                    StatTile("money in") { MoneyText(m.income, cents: false, size: 16, weight: .medium) }
                    StatTile("money out") { MoneyText(m.spending, cents: false, size: 16, weight: .medium) }
                    StatTile("net") { MoneyText(m.net, cents: false, style: .signed, size: 16, weight: .medium) }
                }
                if total > 0 {
                    VStack(spacing: 6) {
                        ForEach(Array(m.categories.prefix(5).enumerated()), id: \.element.id) { i, c in
                            ShareRow(label: Category.label(c.key), amount: c.amount, share: c.amount / total, tone: .series(i))
                        }
                    }
                }
                Button("Cash flow, month by month") { model.insightsSection = .cashflow; model.tab = .insights }
                    .font(JFFont.mono(12, .medium))
            }
        }
    }

    private func upcoming(_ g: Glance) -> some View {
        Panel("coming up", flush: true, actions: {
            HStack(spacing: 6) {
                Fine("14 days")
                MoneyText(g.upcoming.total, cents: false, size: 12, weight: .medium)
            }
        }) {
            if g.upcoming.items.isEmpty {
                Fine("Nothing expected in the next two weeks.").padding(16)
            } else {
                RuledList(g.upcoming.items) { UpcomingRow(item: $0) }
            }
        }
    }

    private var alerts: some View {
        Panel("alerts", flush: true) {
            Loader(height: 80) {
                try await APIClient.shared.alerts()
            } content: { list in
                if list.isEmpty {
                    Fine("No alerts.").padding(16)
                } else {
                    RuledList(Array(list.prefix(5))) { AlertRow(alert: $0) }
                    if list.count > 5 {
                        Button("All \(list.count) alerts") { model.insightsSection = .subscriptions; model.tab = .insights }
                            .font(JFFont.mono(12, .medium))
                            .padding(16)
                    }
                }
            }
        }
    }

    private func groups(_ g: Glance) -> some View {
        Panel("where it sits", flush: true) {
            VStack(spacing: 0) {
                let shown = g.groups.filter { $0.total != 0 }
                ForEach(Array(shown.enumerated()), id: \.element.id) { i, grp in
                    Button {
                        model.tab = .accounts
                    } label: {
                        HStack {
                            Text(grp.label).font(JFFont.sans(15)).foregroundStyle(JF.ink)
                            if grp.is_liability { Badge("owed") }
                            Spacer()
                            MoneyText(grp.total, cents: false, size: 15, weight: .medium)
                            Image(systemName: "chevron.right").font(.system(size: 11, weight: .semibold)).foregroundStyle(JF.ink3)
                        }
                        .padding(.horizontal, 16)
                        .padding(.vertical, 12)
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    if i < shown.count - 1 { Rule().padding(.leading, 16) }
                }
            }
        }
    }
}

/// A connection the bank wants signed in again. The phone can't do that (it
/// is read-only), so it says where to go.
struct AttentionNote: View {
    let items: [Attention]

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: "exclamationmark.circle").foregroundStyle(JF.warn)
            VStack(alignment: .leading, spacing: 4) {
                Text(items.count == 1
                     ? "\(items[0].institution_name ?? "A bank") needs you to sign in again."
                     : "\(items.count) connections need you to sign in again.")
                    .font(JFFont.sans(14, .medium)).foregroundStyle(JF.ink)
                Text("Fix it on the dashboard, Settings → connections. Balances from it may be stale until then.")
                    .font(JFFont.sans(13)).foregroundStyle(JF.ink2)
            }
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(JF.panel)
        .overlay(Rectangle().strokeBorder(JF.warn.opacity(0.6), lineWidth: 1))
    }
}
