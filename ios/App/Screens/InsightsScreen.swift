import JFinancesKit
import SwiftUI

/// The dashboard's Insights tabs: cash flow, spending, subscriptions, net
/// worth and debt, and investing.
struct InsightsScreen: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        @Bindable var model = model
        Screen("Insights") {
            ScrollView(.horizontal) {
                HStack(spacing: 6) {
                    ForEach(InsightsSection.allCases) { s in
                        let on = model.insightsSection == s
                        Button { model.insightsSection = s } label: {
                            Text(s.title)
                                .font(JFFont.mono(12, .medium))
                                .foregroundStyle(on ? JF.accentInk : JF.ink2)
                                .padding(.horizontal, 10)
                                .frame(height: 30)
                                .background(on ? JF.accent : JF.panel)
                                .overlay(Rectangle().strokeBorder(on ? JF.accent : JF.line, lineWidth: 1))
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
            .scrollIndicators(.hidden)
            switch model.insightsSection {
            case .cashflow: CashflowInsights()
            case .spending: SpendingInsights()
            case .subscriptions: SubscriptionInsights()
            case .networth: WealthInsights()
            case .investing:
                PerformancePanel(accountId: nil)
                HoldingsPanel(accountId: nil, limit: 20)
            }
        }
    }
}

// MARK: - the slice

enum SlicePreset {
    static let ranges: [(String, String)] = [("6m", "6m"), ("12m", "12m"), ("ytd", "ytd"), ("ly", "last yr"), ("24m", "24m")]
    static let scopes: [(String, String)] = [("personal", "personal"), ("business", "business"), ("all", "all")]

    static func slice(_ range: String, _ scope: String) -> Slice {
        let cal = Calendar.current
        let today = Date()
        let monthStart = cal.date(from: cal.dateComponents([.year, .month], from: today))!
        func monthsBack(_ n: Int) -> Date { cal.date(byAdding: .month, value: -n, to: monthStart)! }
        let year = cal.component(.year, from: today)
        let jan1 = cal.date(from: DateComponents(year: year, month: 1, day: 1))!
        switch range {
        case "6m": return Slice(from: Fmt.isoDay(monthsBack(5)), to: Fmt.isoDay(today), scope: scope)
        case "ytd": return Slice(from: Fmt.isoDay(jan1), to: Fmt.isoDay(today), scope: scope)
        case "ly":
            let lastJan = cal.date(from: DateComponents(year: year - 1, month: 1, day: 1))!
            let lastDec = cal.date(from: DateComponents(year: year - 1, month: 12, day: 31))!
            return Slice(from: Fmt.isoDay(lastJan), to: Fmt.isoDay(lastDec), scope: scope)
        case "24m": return Slice(from: Fmt.isoDay(monthsBack(23)), to: Fmt.isoDay(today), scope: scope)
        default: return Slice(from: Fmt.isoDay(monthsBack(11)), to: Fmt.isoDay(today), scope: scope)
        }
    }
}

struct SliceControls: View {
    @Binding var range: String
    @Binding var scope: String

    var body: some View {
        FlowLayout(spacing: 8) {
            Chips(options: SlicePreset.ranges, value: $range)
            Chips(options: SlicePreset.scopes, value: $scope)
        }
    }
}

// MARK: - cash flow

struct CashflowInsights: View {
    @AppStorage("jf.ins.range") private var range = "12m"
    @AppStorage("jf.ins.scope") private var scope = "personal"

    var body: some View {
        let slice = SlicePreset.slice(range, scope)
        SliceControls(range: $range, scope: $scope)
        Loader(id: slice, height: 420) {
            try await APIClient.shared.cashflow(slice)
        } content: { cf in
            VStack(spacing: 12) {
                Panel("cash flow") {
                    VStack(alignment: .leading, spacing: 14) {
                        HStack(spacing: 12) {
                            StatTile("money in") { MoneyText(cf.totals.income, cents: false, size: 16, weight: .medium) }
                            StatTile("money out") { MoneyText(cf.totals.spending, cents: false, size: 16, weight: .medium) }
                            StatTile("net") { MoneyText(cf.totals.net, cents: false, style: .signed, size: 16, weight: .medium) }
                        }
                        if cf.periods.isEmpty { Fine("Nothing in this range.") } else { FlowBarsChart(periods: cf.periods) }
                        HStack(spacing: 12) {
                            StatTile("avg in / month") { MoneyText(cf.averages.income, cents: false, size: 13) }
                            StatTile("avg out / month") { MoneyText(cf.averages.spending, cents: false, size: 13) }
                            StatTile("kept") {
                                Text(Fmt.pct(cf.totals.savings_rate, digits: 0))
                                    .font(JFFont.mono(13)).foregroundStyle(JF.ink).figure(size: 13)
                            }
                        }
                    }
                }
                if !cf.income_sources.isEmpty {
                    Panel("money in, by source", flush: true) {
                        RuledList(cf.income_sources) { s in
                            HStack {
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(s.label).font(JFFont.sans(14, .medium)).foregroundStyle(JF.ink).lineLimit(1)
                                    if let n = s.count { Fine("\(n) deposits") }
                                }
                                Spacer()
                                MoneyText(s.amount, cents: false, size: 14, weight: .medium)
                            }
                            .padding(.vertical, 8)
                        }
                    }
                }
                let total = cf.spending_categories.reduce(0) { $0 + $1.amount }
                if total > 0 {
                    Panel("where it went") {
                        VStack(spacing: 6) {
                            ForEach(Array(cf.spending_categories.enumerated()), id: \.element.id) { i, c in
                                ShareRow(label: Category.label(c.key), amount: c.amount, share: c.amount / total,
                                         tone: c.key == "OTHER" ? .ink : .series(i))
                            }
                        }
                    }
                }
            }
        }
    }
}

// MARK: - spending

struct SpendingInsights: View {
    @AppStorage("jf.ins.range") private var range = "12m"
    @AppStorage("jf.ins.scope") private var scope = "personal"
    @State private var category: String?

    private struct MerchantKey: Hashable { let slice: Slice; let category: String? }

    var body: some View {
        let slice = SlicePreset.slice(range, scope)
        SliceControls(range: $range, scope: $scope)
        Loader(id: slice, height: 360) {
            try await APIClient.shared.spending(slice, top: 6)
        } content: { sp in
            Panel("spending by category") {
                VStack(alignment: .leading, spacing: 14) {
                    Readout("total", value: Fmt.money(sp.total, cents: false), size: 36)
                    if sp.periods.count > 0 { StackedSpendingChart(spending: sp) }
                    VStack(spacing: 0) {
                        ForEach(Array(sp.series.enumerated()), id: \.element.id) { i, s in
                            let on = category == s.key
                            Button {
                                category = (on || s.key == "OTHER") ? nil : s.key
                            } label: {
                                HStack(spacing: 10) {
                                    Rectangle().fill(s.key == "OTHER" ? JF.other : JF.seriesColor(i)).frame(width: 8, height: 8)
                                    Text(Category.label(s.key)).font(JFFont.sans(14, on ? .semibold : .regular)).foregroundStyle(JF.ink)
                                    Spacer()
                                    MoneyText(s.total, cents: false, size: 13)
                                    if sp.total > 0 { Text(Fmt.pct(s.total / sp.total, digits: 0)).font(JFFont.mono(11)).foregroundStyle(JF.ink3).frame(width: 36, alignment: .trailing) }
                                }
                                .padding(.vertical, 7)
                                .contentShape(Rectangle())
                            }
                            .buttonStyle(.plain)
                        }
                    }
                    Fine("Tap a category to see its merchants.")
                }
            }
        }
        Loader(id: MerchantKey(slice: slice, category: category), height: 300) {
            try await APIClient.shared.merchants(slice, category: category, top: 20)
        } content: { list in
            Panel(category.map { "top merchants · \(Category.label($0))" } ?? "top merchants", flush: true, actions: {
                if category != nil { Button("all") { category = nil }.font(JFFont.mono(12, .medium)) }
            }) {
                if list.isEmpty { Fine("No merchants in this range.").padding(16) }
                RuledList(list) { m in
                    HStack(spacing: 10) {
                        VStack(alignment: .leading, spacing: 2) {
                            HStack(spacing: 6) {
                                Text(m.label).font(JFFont.sans(14, .medium)).foregroundStyle(JF.ink).lineLimit(1)
                                if m.is_new { Badge("new", tone: .accent) }
                            }
                            Text("\(m.count)× · avg \(Fmt.money(m.average, cents: false)) · \(Category.label(m.category))")
                                .font(JFFont.mono(11)).foregroundStyle(JF.ink3).lineLimit(1).figure(size: 11)
                        }
                        Spacer(minLength: 8)
                        PixelBars(m.trend.map(\.wrappedValue), color: JF.ink3).frame(width: 44, height: 18)
                        MoneyText(m.total, cents: false, size: 14, weight: .medium)
                    }
                    .padding(.vertical, 8)
                }
            }
        }
    }
}

// MARK: - subscriptions

struct SubscriptionInsights: View {
    var body: some View {
        Loader(height: 300) {
            try await APIClient.shared.recurring()
        } content: { r in
            let streams = r.streams.filter { $0.status != "dismissed" }
                .sorted { ($0.status == "confirmed" ? 0 : 1, $0.next_date) < ($1.status == "confirmed" ? 0 : 1, $1.next_date) }
            Panel("subscriptions", flush: true) {
                VStack(alignment: .leading, spacing: 0) {
                    HStack(spacing: 12) {
                        StatTile("confirmed / month") { MoneyText(r.monthly_confirmed, cents: false, size: 18, weight: .medium) }
                        StatTile("unreviewed / month") { MoneyText(r.monthly_detected, cents: false, size: 18, weight: .medium) }
                    }
                    .padding(16)
                    Rule()
                    if streams.isEmpty { Fine("No recurring charges found yet.").padding(16) }
                    RuledList(streams) { s in StreamRow(stream: s) }
                    Rule()
                    Fine("Confirm or dismiss subscriptions on the dashboard, Insights → Subscriptions.").padding(16)
                }
            }
        }
        Loader(height: 160) {
            try await APIClient.shared.upcoming(days: 30)
        } content: { up in
            Panel("next 30 days", flush: true, actions: { MoneyText(up.total, cents: false, size: 12, weight: .medium) }) {
                if up.items.isEmpty { Fine("Nothing expected.").padding(16) }
                RuledList(up.items) { UpcomingRow(item: $0) }
            }
        }
        Loader(height: 120) {
            try await APIClient.shared.alerts()
        } content: { list in
            Panel("alerts", flush: true, actions: { Fine("\(list.count)") }) {
                if list.isEmpty { Fine("No alerts in the last 60 days.").padding(16) }
                RuledList(list) { AlertRow(alert: $0) }
            }
        }
    }
}

struct StreamRow: View {
    let stream: RecurringStream

    var body: some View {
        HStack(spacing: 10) {
            VStack(alignment: .leading, spacing: 3) {
                HStack(spacing: 6) {
                    Text(stream.label).font(JFFont.sans(14, .medium)).foregroundStyle(JF.ink).lineLimit(1)
                    if stream.is_business == true { BusinessMark() }
                    if stream.status == "detected" { Badge("unreviewed") }
                    if stream.state == "lapsed" { Badge("lapsed", tone: .warn) }
                    if let prev = stream.previous_amount, prev != stream.amount { Badge(stream.amount > prev ? "price up" : "price down", tone: .accent) }
                }
                Text("\(stream.cadence) · next \(Fmt.date(stream.next_date))\(stream.account_name.map { " · \($0)" } ?? "")")
                    .font(JFFont.mono(11)).foregroundStyle(JF.ink3).lineLimit(1)
            }
            Spacer(minLength: 8)
            VStack(alignment: .trailing, spacing: 2) {
                MoneyText(stream.amount, size: 14, weight: .medium)
                if stream.cadence != "monthly" {
                    HStack(spacing: 3) {
                        MoneyText(stream.monthly, size: 11)
                        Text("/mo").font(JFFont.mono(11)).foregroundStyle(JF.ink3)
                    }
                }
            }
        }
        .padding(.vertical, 8)
    }
}

// MARK: - net worth and debt

struct WealthInsights: View {
    @State private var range = "2y"
    @State private var extra = 0.0
    @State private var cardRange = "1y"

    var body: some View {
        Panel("net worth by kind", actions: {
            Chips(options: [("1y", "1y"), ("2y", "2y"), ("5y", "5y")], value: $range)
        }) {
            Loader(id: range, height: 300) {
                try await APIClient.shared.netWorthByClass(range: range)
            } content: { d in
                if let last = d.points.last {
                    VStack(alignment: .leading, spacing: 14) {
                        HStack(spacing: 12) {
                            StatTile("owned") { MoneyText(d.value(last, "assets"), cents: false, size: 15, weight: .medium) }
                            StatTile("owed") { MoneyText(d.value(last, "liabilities"), cents: false, size: 15, weight: .medium) }
                            StatTile("net worth") { MoneyText(d.value(last, "net"), cents: false, size: 15, weight: .medium) }
                        }
                        ClassBarsChart(data: d)
                    }
                } else {
                    Fine("Nothing yet.")
                }
            }
        }
        Loader(height: 160) {
            try await APIClient.shared.homes()
        } content: { homes in
            if !homes.isEmpty {
                Panel("homes and equity") {
                    VStack(alignment: .leading, spacing: 18) {
                        ForEach(homes) { h in HomeBlock(home: h) }
                    }
                }
            }
        }
        Panel("loan payoff", actions: {
            Chips(options: [(0.0, "+$0"), (100.0, "+100"), (250.0, "+250"), (500.0, "+500"), (1000.0, "+1k")], value: $extra)
        }) {
            Loader(id: extra, height: 200) {
                try await APIClient.shared.loans(extra: extra)
            } content: { loans in
                VStack(alignment: .leading, spacing: 18) {
                    if loans.isEmpty { Fine("No loans.") }
                    ForEach(loans) { l in LoanBlock(loan: l) }
                    Fine("Chips add that much to every monthly payment, to see how much sooner each loan ends.")
                }
            }
        }
        Panel("cards", actions: {
            Chips(options: [("1y", "1y"), ("2y", "2y"), ("5y", "5y")], value: $cardRange)
        }) {
            Loader(id: cardRange, height: 160) {
                try await APIClient.shared.cards(range: cardRange)
            } content: { c in
                if c.cards.isEmpty { Fine("No cards.") } else {
                    VStack(alignment: .leading, spacing: 14) {
                        HStack(spacing: 12) {
                            StatTile("utilization", note: "all cards") {
                                Text(Fmt.pct(c.overall.last?.utilization, digits: 0)).font(JFFont.mono(15, .medium)).foregroundStyle(JF.ink).figure(size: 15)
                            }
                            StatTile("interest", note: "in range") { MoneyText(c.totals.interest, cents: false, size: 15, weight: .medium) }
                            StatTile("fees", note: "in range") { MoneyText(c.totals.fees, cents: false, size: 15, weight: .medium) }
                        }
                        ForEach(c.cards) { card in
                            VStack(alignment: .leading, spacing: 5) {
                                HStack {
                                    Text(card.name).font(JFFont.sans(14)).foregroundStyle(JF.ink).lineLimit(1)
                                    if let m = card.mask { Text("··\(m)").font(JFFont.mono(11)).foregroundStyle(JF.ink3) }
                                    Spacer()
                                    MoneyText(card.balance, cents: false, size: 13)
                                }
                                if let u = card.utilization {
                                    PixelMeter(ratio: min(1, u), cells: 32, tone: u >= 0.5 ? .neg : u >= 0.3 ? .warn : .accent, height: 6)
                                    Fine("\(Fmt.pct(u, digits: 0)) of \(card.limit.map { Fmt.money($0, cents: false) } ?? "limit")")
                                } else {
                                    Fine("no limit reported")
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

struct HomeBlock: View {
    let home: Home

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(home.name).font(JFFont.sans(15, .semibold)).foregroundStyle(JF.ink)
                Spacer()
                Fine("equity")
                MoneyText(home.equity, cents: false, size: 15, weight: .medium)
            }
            KeyValueRow("value") { MoneyText(home.value, cents: false) }
            KeyValueRow("owed") { MoneyText(home.owed, cents: false) }
            ForEach(home.loans) { l in
                KeyValueRow("loan") {
                    HStack(spacing: 4) {
                        Text(l.name + (l.mask.map { " ··\($0)" } ?? "")).lineLimit(1)
                        if let r = l.rate { Text(Fmt.pct(r, digits: 3, ratio: false)).font(JFFont.mono(12)).foregroundStyle(JF.ink3) }
                    }
                }
            }
            if let ltv = home.ltv {
                PixelMeter(ratio: min(1, ltv), cells: 32, tone: ltv > 0.8 ? .neg : ltv > 0.6 ? .warn : .pos, height: 6)
                Fine("\(Fmt.pct(ltv, digits: 0)) loan-to-value")
            }
            if home.history.count >= 2 {
                HStack {
                    Fine("equity, monthly")
                    Spacer()
                    PixelSparkline(home.history.map(\.equity)).frame(width: 140, height: 22)
                }
            }
        }
    }
}

struct LoanBlock: View {
    let loan: LoanPayoff

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text(loan.name).font(JFFont.sans(15, .semibold)).foregroundStyle(JF.ink).lineLimit(1)
                Spacer()
                MoneyText(loan.balance, cents: false, size: 15, weight: .medium)
            }
            if let s = loan.schedule {
                if let r = loan.rate { KeyValueRow("rate") { Text(Fmt.pct(r, digits: 3, ratio: false)).font(JFFont.mono(14)) } }
                KeyValueRow("payment") { MoneyText(s.payment) }
                if let payoff = s.payoff {
                    KeyValueRow("paid off") { Text("\(Fmt.date(payoff, year: true))\(s.months.map { " · \($0) mo" } ?? "")").font(JFFont.mono(13)) }
                }
                if let i = s.interest { KeyValueRow("interest left") { MoneyText(i, cents: false) } }
                if let w = loan.what_if {
                    Text("With \(Fmt.money(w.extra, cents: false)) more a month: paid off \(Fmt.date(w.payoff, year: true)), \(w.months_saved) months sooner, saving \(Fmt.money(w.interest_saved, cents: false)).")
                        .font(JFFont.sans(13)).foregroundStyle(JF.pos).figure(size: 13)
                }
            } else if let note = loan.note {
                Fine(note)
            }
        }
    }
}

// MARK: - investing

/// Time-weighted return with benchmarks to check against.
struct PerformancePanel: View {
    let accountId: String?
    @AppStorage("jf.perf.range") private var range = "1y"
    @AppStorage("jf.perf.bench") private var benchCSV = "sp500"

    private struct Key: Hashable { let r: String; let b: String; let a: String? }
    private var benches: [String] { benchCSV.split(separator: ",").map(String.init).filter { !$0.isEmpty } }

    var body: some View {
        Panel(accountId == nil ? "performance" : "this account's performance", actions: {
            Chips(options: [("3m", "3m"), ("6m", "6m"), ("1y", "1y"), ("2y", "2y"), ("5y", "5y")], value: $range)
        }) {
            Loader(id: Key(r: range, b: benchCSV, a: accountId), height: 260) {
                try await APIClient.shared.performance(range: range, accountId: accountId, benchmarks: benches)
            } content: { p in
                VStack(alignment: .leading, spacing: 14) {
                    if let last = p.series.last {
                        Readout("time-weighted return, \(range)", value: Fmt.pct(last.return, signed: true), size: 36,
                                delta: AnyView(HStack(spacing: 6) {
                                    Fine("value")
                                    MoneyText(last.value, cents: false, size: 12, weight: .medium)
                                }))
                        ReturnsChart(lines: lines(p))
                    } else {
                        Fine("No investment history in this range yet.")
                    }
                    FlowLayout(spacing: 6) {
                        ForEach(Array(p.available.filter(\.available).enumerated()), id: \.element.id) { i, b in
                            ToggleChip(label: b.label, color: JF.seriesColor(i), on: benches.contains(b.key)) { toggle(b.key) }
                        }
                    }
                    if let est = p.estimated_before {
                        Fine("Before \(Fmt.date(est, year: true)) holdings are rebuilt from trades.")
                    }
                }
            }
        }
    }

    private func lines(_ p: Performance) -> [ReturnsChart.Line] {
        let order = p.available.filter(\.available).map(\.key)
        var out = [ReturnsChart.Line(key: "portfolio", label: accountId == nil ? "portfolio" : "account", color: JF.accent,
                                     points: p.series.compactMap { x in Fmt.day(x.date).map { DatedValue(date: $0, value: x.return) } },
                                     emphasis: true)]
        for b in p.benchmarks {
            let i = order.firstIndex(of: b.key) ?? 5
            out.append(.init(key: b.key, label: b.label, color: JF.seriesColor(i),
                             points: b.points.compactMap { x in Fmt.day(x.date).map { DatedValue(date: $0, value: x.return) } },
                             emphasis: false))
        }
        return out
    }

    private func toggle(_ key: String) {
        var set = benches
        if let i = set.firstIndex(of: key) { set.remove(at: i) } else { set.append(key) }
        benchCSV = set.joined(separator: ",")
    }
}
