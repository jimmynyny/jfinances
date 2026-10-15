import JFinancesKit
import SwiftUI

/// The dashboard's Insights tabs: cash flow, spending, subscriptions, net
/// worth and debt, and investing.
struct InsightsScreen: View {
    @Environment(AppModel.self) private var model
    /// A number tapped twice: its transactions, pushed on this tab.
    @State private var drill: DrillTarget?

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
            .panelSpan()
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
        .environment(\.openDrill) { drill = $0 }
        .navigationDestination(item: $drill) { DrillScreen(target: $0) }
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

    /// The days the period starting `start` covers at `grain`, inside the slice.
    static func periodRange(_ start: String, grain: String, slice: Slice) -> (from: String, to: String) {
        let cal = Calendar.current
        let d = Fmt.day(start) ?? Date()
        let months = grain == "quarter" ? 3 : grain == "year" ? 12 : 1
        let last = Fmt.isoDay(cal.date(byAdding: .day, value: -1, to: cal.date(byAdding: .month, value: months, to: d)!)!)
        return (start < slice.from ? slice.from : start, last > slice.to ? slice.to : last)
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
        .panelSpan()
    }
}

// MARK: - cash flow

/// A trailing chevron: this row opens its transactions.
struct OpensMark: View {
    var body: some View {
        Image(systemName: "chevron.right").font(.system(size: 10, weight: .semibold)).foregroundStyle(JF.ink3)
    }
}

struct CashflowInsights: View {
    @Environment(\.openDrill) private var openDrill
    @AppStorage("jf.ins.range") private var range = "12m"
    @AppStorage("jf.ins.scope") private var scope = "personal"

    var body: some View {
        let slice = SlicePreset.slice(range, scope)
        SliceControls(range: $range, scope: $scope)
        Loader(id: slice, height: 420) {
            try await APIClient.shared.cashflow(slice)
        } content: { cf in
            // Its three panels share one load; on a wide screen they still take columns.
            PanelStack {
                Panel("cash flow") {
                    VStack(alignment: .leading, spacing: 14) {
                        HStack(spacing: 12) {
                            StatTile("money in") { MoneyText(cf.totals.income, cents: false, size: 16, weight: .medium) }
                            StatTile("money out") { MoneyText(cf.totals.spending, cents: false, size: 16, weight: .medium) }
                            StatTile("net") { MoneyText(cf.totals.net, cents: false, style: .signed, size: 16, weight: .medium) }
                        }
                        if cf.periods.isEmpty {
                            Fine("Nothing in this range.")
                        } else {
                            FlowBarsChart(periods: cf.periods) { p, flow in
                                let r = SlicePreset.periodRange(p.period, grain: cf.grain, slice: slice)
                                openDrill(DrillTarget(slice: slice, drill: Drill(flow: flow, from: r.from, to: r.to),
                                                      title: "\(p.label) · money \(flow == "income" ? "in" : "out")"))
                            }
                        }
                        HStack(spacing: 12) {
                            StatTile("avg in / month") { MoneyText(cf.averages.income, cents: false, size: 13) }
                            StatTile("avg out / month") { MoneyText(cf.averages.spending, cents: false, size: 13) }
                            StatTile("kept") {
                                Text(Fmt.pct(cf.totals.savings_rate, digits: 0))
                                    .font(JFFont.mono(13)).foregroundStyle(JF.ink).figure(size: 13)
                            }
                        }
                        if !cf.periods.isEmpty { Fine("Tap a bar for its numbers, again for its transactions.") }
                    }
                }
                let flow = flowNodes(cf, slice)
                if !flow.sources.isEmpty || !flow.uses.isEmpty {
                    Panel("money flow") {
                        VStack(alignment: .leading, spacing: 10) {
                            MoneyFlowChart(sources: flow.sources, uses: flow.uses, centerLabel: "income") {
                                openDrill(DrillTarget(slice: slice, drill: Drill(flow: "income"), title: "Income"))
                            }
                            Fine("Tap a name to light its path, again for its transactions.")
                        }
                    }
                }
                if !cf.income_sources.isEmpty {
                    Panel("money in, by source", flush: true) {
                        RuledList(cf.income_sources) { s in
                            Button {
                                openDrill(DrillTarget(slice: slice, drill: Drill(flow: "income", merchant: s.label, incomeKind: s.kind), title: s.label))
                            } label: {
                                HStack(spacing: 10) {
                                    VStack(alignment: .leading, spacing: 2) {
                                        Text(s.label).font(JFFont.sans(14, .medium)).foregroundStyle(JF.ink).lineLimit(1)
                                        Fine([s.kind, s.count.map { "\($0) deposit\($0 == 1 ? "" : "s")" }].compactMap { $0 }.joined(separator: " · "))
                                    }
                                    Spacer()
                                    MoneyText(s.amount, cents: false, size: 14, weight: .medium)
                                    OpensMark()
                                }
                                .padding(.vertical, 8)
                                .contentShape(Rectangle())
                            }
                            .buttonStyle(.plain)
                        }
                    }
                }
            }
        }
        .panelSpan()
    }

    /// Income sources -> income -> spending categories, plus what was saved (or
    /// drawn from savings); each node opens the transactions it is made of.
    private func flowNodes(_ d: Cashflow, _ slice: Slice) -> (sources: [FlowNodeSpec], uses: [FlowNodeSpec]) {
        func open(_ drill: Drill, _ title: String) -> () -> Void {
            { openDrill(DrillTarget(slice: slice, drill: drill, title: title)) }
        }
        let head = Array(d.income_sources.prefix(5))
        let rest = d.income_sources.dropFirst(5).reduce(0) { $0 + $1.amount }
        var sources = head.map { s in
            FlowNodeSpec(key: "in:\(s.kind):\(s.label)", label: s.label, value: s.amount, color: JF.divPos,
                         open: open(Drill(flow: "income", merchant: s.label, incomeKind: s.kind), s.label))
        }
        if rest > 0 {
            sources.append(FlowNodeSpec(key: "in:other", label: "other income", value: rest, color: JF.divPos,
                                        open: open(Drill(flow: "income", notSource: head.map { "\($0.kind):\($0.label)" }), "Other income")))
        }
        let named = d.spending_categories.filter { $0.key != "OTHER" }.map(\.key)
        var uses = d.spending_categories.enumerated().map { i, c in
            FlowNodeSpec(key: "out:\(c.key)", label: Category.label(c.key), value: c.amount,
                         color: c.key == "OTHER" ? JF.other : JF.seriesColor(i),
                         open: open(c.key == "OTHER" ? Drill(flow: "spending", notCategory: named) : Drill(flow: "spending", category: c.key),
                                    Category.label(c.key).capitalizedFirst))
        }
        if d.totals.net > 0 {
            uses.append(FlowNodeSpec(key: "saved", label: "saved", value: d.totals.net, color: JF.divPos,
                                     open: open(Drill(flow: "all"), "Income and spending")))
        }
        if d.totals.net < 0 {
            sources.append(FlowNodeSpec(key: "in:savings", label: "from savings", value: -d.totals.net, color: JF.ink3,
                                        open: open(Drill(flow: "spending", largestFirst: true, why: "savings"), "From savings")))
        }
        return (sources, uses)
    }
}

extension String {
    /// "food and drink" -> "Food and drink", for a screen title.
    var capitalizedFirst: String { prefix(1).uppercased() + dropFirst() }
}

// MARK: - spending

struct SpendingInsights: View {
    @Environment(\.openDrill) private var openDrill
    @AppStorage("jf.ins.range") private var range = "12m"
    @AppStorage("jf.ins.scope") private var scope = "personal"
    /// A category to look inside: its kinds in the chart, its merchants below.
    @State private var category: String?
    @State private var hidden: Set<String> = []
    /// The top categories, for the picker (from the last look at all of them).
    @State private var topKeys: [String] = []

    private struct Key: Hashable { let slice: Slice; let category: String? }

    private func label(_ key: String) -> String { Category.label(key, primary: category) }

    /// The rows a series is made of: inside a category, one of its kinds; "OTHER" is every one not shown.
    private func drill(_ key: String, _ sp: Spending) -> Drill {
        let named = sp.series.filter { $0.key != "OTHER" }.map(\.key)
        var d = Drill(flow: "spending", category: category)
        if key == "OTHER" {
            if category != nil { d.notDetailed = named } else { d.notCategory = named }
        } else if category != nil {
            d.detailed = key
        } else {
            d.category = key
        }
        return d
    }

    var body: some View {
        let slice = SlicePreset.slice(range, scope)
        SliceControls(range: $range, scope: $scope)
        Loader(id: Key(slice: slice, category: category), height: 360) {
            let sp = try await APIClient.shared.spending(slice, category: category, top: 6)
            if category == nil { topKeys = sp.series.map(\.key).filter { $0 != "OTHER" } }
            return sp
        } content: { sp in
            Panel(category.map { "spending · \(Category.label($0))" } ?? "spending by category", actions: { categoryMenu }) {
                VStack(alignment: .leading, spacing: 14) {
                    Readout("total", value: Fmt.money(sp.total, cents: false), size: 36)
                    if sp.periods.count > 0 {
                        LegendToggles(items: sp.series.enumerated().map { i, s in
                            .init(key: s.key, label: label(s.key), color: s.key == "OTHER" ? JF.other : JF.seriesColor(i))
                        }, hidden: $hidden)
                        StackedSpendingChart(spending: sp, hidden: hidden, labelFor: label) { key, period in
                            let r = SlicePreset.periodRange(period.period, grain: sp.grain, slice: slice)
                            var d = drill(key, sp)
                            d.from = r.from
                            d.to = r.to
                            openDrill(DrillTarget(slice: slice, drill: d, title: "\(label(key).capitalizedFirst) · \(period.label)"))
                        }
                    }
                    VStack(spacing: 0) {
                        ForEach(Array(sp.series.enumerated()), id: \.element.id) { i, s in
                            Button {
                                openDrill(DrillTarget(slice: slice, drill: drill(s.key, sp), title: label(s.key).capitalizedFirst))
                            } label: {
                                HStack(spacing: 10) {
                                    Rectangle().fill(s.key == "OTHER" ? JF.other : JF.seriesColor(i)).frame(width: 8, height: 8)
                                    Text(label(s.key)).font(JFFont.sans(14)).foregroundStyle(JF.ink).lineLimit(1)
                                    Spacer()
                                    MoneyText(s.total, cents: false, size: 13)
                                    if sp.total > 0 {
                                        Text(Fmt.pct(s.total / sp.total, digits: 0)).font(JFFont.mono(11)).foregroundStyle(JF.ink3)
                                            .frame(width: 36, alignment: .trailing).figure(size: 11)
                                    }
                                    OpensMark()
                                }
                                .padding(.vertical, 7)
                                .contentShape(Rectangle())
                            }
                            .buttonStyle(.plain)
                        }
                    }
                    Fine(category == nil
                         ? "Tap a category for its transactions, or pick one above for its kinds and merchants. A bar: once for its numbers, again for its transactions."
                         : "Tap a kind for its transactions. A bar: once for its numbers, again for its transactions.")
                }
            }
        }
        Loader(id: Key(slice: slice, category: category), height: 300) {
            try await APIClient.shared.merchants(slice, category: category, top: 20)
        } content: { list in
            Panel(category.map { "top merchants · \(Category.label($0))" } ?? "top merchants", flush: true) {
                if list.isEmpty { Fine("No merchants in this range.").padding(16) }
                RuledList(list) { m in
                    Button {
                        // A merchant's total counts purchases, not refunds: so does its list.
                        openDrill(DrillTarget(slice: slice, drill: Drill(flow: "spending", category: category, merchant: m.label, direction: "out"),
                                              title: m.label))
                    } label: {
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
                            OpensMark()
                        }
                        .padding(.vertical, 8)
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                }
            }
        }
    }

    private var categoryMenu: some View {
        Menu {
            Button("All categories") { pick(nil) }
            ForEach(topKeys, id: \.self) { k in Button(Category.label(k)) { pick(k) } }
        } label: {
            FilterChip(text: category.map { Category.label($0) } ?? "all", active: category != nil)
        }
        .accessibilityLabel("Category, \(category.map { Category.label($0) } ?? "all")")
    }

    private func pick(_ key: String?) {
        category = key
        hidden = []
    }
}

// MARK: - subscriptions

struct SubscriptionInsights: View {
    @Environment(AppModel.self) private var model
    @State private var renaming: RecurringStream?
    @State private var looking = false
    @State private var toast: String?

    var body: some View {
        Loader(height: 300) {
            try await APIClient.shared.recurring()
        } content: { r in
            // The server lists recurring ones first, then those to review, each soonest next charge first.
            let streams = r.streams.filter { $0.state == "active" && $0.status != "dismissed" }
                .sorted { ($0.status == "confirmed" ? 0 : 1, $0.next_date) < ($1.status == "confirmed" ? 0 : 1, $1.next_date) }
            Panel("subscriptions", flush: true, actions: {
                Button {
                    Task { await look() }
                } label: {
                    if looking { ProgressView() } else { Text("Look for new ones") }
                }
                .font(JFFont.mono(12, .medium))
                .disabled(looking)
            }) {
                VStack(alignment: .leading, spacing: 0) {
                    HStack(spacing: 12) {
                        StatTile("recurring / month") { MoneyText(r.monthly_confirmed, cents: false, size: 18, weight: .medium) }
                        StatTile("to review / month") { MoneyText(r.monthly_detected, cents: false, size: 18, weight: .medium) }
                    }
                    .padding(16)
                    Rule()
                    if streams.isEmpty { Fine("No recurring charges found yet.").padding(16) }
                    RuledList(streams) { s in
                        Menu {
                            if s.status != "confirmed" { Button("Recurring", systemImage: "checkmark") { Task { await verdict(s, "confirmed") } } }
                            if s.status != "detected" { Button("Not sure yet", systemImage: "questionmark") { Task { await verdict(s, "detected") } } }
                            Button("Rename…", systemImage: "pencil") { renaming = s }
                            Button("Not recurring", systemImage: "xmark", role: .destructive) { Task { await verdict(s, "dismissed") } }
                        } label: {
                            StreamRow(stream: s)
                        }
                        .tint(JF.ink)
                    }
                    Rule()
                    Fine("Tap one to mark it recurring or not, or to name it.").padding(16)
                }
            }
        }
        .toast($toast)
        .sheet(item: $renaming) { s in
            RenameStreamSheet(stream: s) { toast = "Renamed" }
        }
        Loader(height: 160) {
            try await APIClient.shared.upcoming(days: 30)
        } content: { up in
            Panel("next 30 days", flush: true, actions: { MoneyText(up.total, cents: false, size: 12, weight: .medium) }) {
                if up.items.isEmpty { Fine("Nothing expected.").padding(16) }
                RuledList(up.items) { UpcomingRow(item: $0) }
            }
        }
        AlertsPanel(limit: nil)
    }

    private func verdict(_ s: RecurringStream, _ status: String) async {
        do {
            _ = try await APIClient.shared.patchRecurring(id: s.id, JSONBody(["status": .string(status)]))
            model.changed()
            toast = status == "confirmed" ? "Marked recurring" : status == "dismissed" ? "Marked not recurring" : "Back to review"
        } catch let e as APIError {
            model.handle(e)
            toast = e.errorDescription
        } catch {}
    }

    private func look() async {
        looking = true
        defer { looking = false }
        do {
            let n = try await APIClient.shared.detectRecurring()
            model.changed()
            toast = n == 0 ? "Nothing new found" : "Found \(n) new"
        } catch let e as APIError {
            model.handle(e)
            toast = e.errorDescription
        } catch {}
    }
}

/// A subscription's name, as it reads in lists; blank goes back to the merchant's.
struct RenameStreamSheet: View {
    let stream: RecurringStream
    let onSaved: () -> Void
    @State private var name: String

    init(stream: RecurringStream, onSaved: @escaping () -> Void) {
        self.stream = stream
        self.onSaved = onSaved
        _name = State(initialValue: stream.name ?? "")
    }

    var body: some View {
        FormSheet(title: "Rename", save: {
            _ = try await APIClient.shared.patchRecurring(id: stream.id, JSONBody(["name": .text(name)]))
            onSaved()
        }) {
            Panel(stream.merchant.lowercased()) {
                Field(label: "name", text: $name, placeholder: stream.merchant, capitalization: .words, help: "Blank goes back to the merchant's name.")
            }
        }
    }
}

/// Alerts, each dismissable with a tap, or all at once (Insights → Subscriptions
/// and the Overview).
struct AlertsPanel: View {
    @Environment(AppModel.self) private var model
    /// How many to show (the Overview shows five), or every one.
    let limit: Int?
    @State private var toast: String?
    @State private var dismissing = false

    var body: some View {
        Loader(height: 120) {
            try await APIClient.shared.alerts()
        } content: { list in
            Panel("alerts", flush: true, actions: {
                if !list.isEmpty {
                    Button {
                        Task { await dismissAll() }
                    } label: {
                        if dismissing { ProgressView() } else { Text("Dismiss all") }
                    }
                    .font(JFFont.mono(12, .medium))
                    .disabled(dismissing)
                }
            }) {
                if list.isEmpty { Fine(limit == nil ? "No alerts in the last 60 days." : "No alerts.").padding(16) }
                RuledList(limit.map { Array(list.prefix($0)) } ?? list) { a in
                    Menu {
                        Button("Dismiss", systemImage: "xmark") { Task { await dismiss(a) } }
                    } label: {
                        AlertRow(alert: a)
                    }
                    .tint(JF.ink)
                }
                if let limit, list.count > limit {
                    Button("All \(list.count) alerts") { model.insightsSection = .subscriptions; model.tab = .insights }
                        .font(JFFont.mono(12, .medium))
                        .padding(16)
                }
            }
        }
        .toast($toast)
    }

    private func dismiss(_ a: MoneyAlert) async {
        do {
            try await APIClient.shared.dismissAlert(key: a.key)
            model.changed()
        } catch let e as APIError {
            model.handle(e)
            toast = e.errorDescription
        } catch {}
    }

    private func dismissAll() async {
        dismissing = true
        defer { dismissing = false }
        do {
            let n = try await APIClient.shared.dismissAllAlerts()
            model.changed()
            toast = "Dismissed \(n)"
        } catch let e as APIError {
            model.handle(e)
            toast = e.errorDescription
        } catch {}
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
                    if stream.status == "detected" { Badge("to review") }
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
    /// The accounts marked business, to mark them in these lists.
    @State private var business: Set<String> = []

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
        .task {
            if let all = try? await APIClient.shared.accounts() { business = Set(all.filter { $0.is_business == true }.map(\.id)) }
        }
        Loader(height: 160) {
            try await APIClient.shared.homes()
        } content: { homes in
            if !homes.isEmpty {
                Panel("homes and equity") {
                    VStack(alignment: .leading, spacing: 18) {
                        ForEach(homes) { h in HomeBlock(home: h, business: business.contains(h.id)) }
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
                    ForEach(loans) { l in LoanBlock(loan: l, business: business.contains(l.id)) }
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
                                HStack(spacing: 6) {
                                    Text((card.institution_name.map { "\($0): " } ?? "") + Account.nameWithoutMask(card.name, card.mask))
                                        .font(JFFont.sans(14)).foregroundStyle(JF.ink).lineLimit(1)
                                    if card.is_business == true || business.contains(card.id) { BusinessMark() }
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
    var business = false

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 6) {
                Text(home.name).font(JFFont.sans(15, .semibold)).foregroundStyle(JF.ink)
                if business { BusinessMark() }
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
    var business = false

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 6) {
                Text(loan.name).font(JFFont.sans(15, .semibold)).foregroundStyle(JF.ink).lineLimit(1)
                if business { BusinessMark() }
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
