import JFinancesKit
import SwiftUI

/// A number on Insights, opened: the slice it came from, how Insights grouped
/// it, and a short name for the screen (the web's lib/drill.ts links).
struct DrillTarget: Hashable, Identifiable {
    let slice: Slice
    let drill: Drill
    let title: String
    var id: Self { self }
}

private struct OpenDrillKey: EnvironmentKey {
    static let defaultValue: (DrillTarget) -> Void = { _ in }
}

extension EnvironmentValues {
    /// Opens the transactions behind an Insights number; InsightsScreen pushes them.
    var openDrill: (DrillTarget) -> Void {
        get { self[OpenDrillKey.self] }
        set { self[OpenDrillKey.self] = newValue }
    }
}

enum DrillWords {
    /// What a list opened from Insights is for, when its numbers alone don't say.
    static let why = [
        "savings": "Spending beyond income in this range is drawn from savings (or debt). These are the spending transactions, biggest first: a transfer to your own account, a reimbursement or income filed as spending makes the gap look bigger; fix those on the dashboard. Income that lands in an account that isn't connected is missing altogether: import that account's history.",
    ]

    private static let weekdays = ["Mondays", "Tuesdays", "Wednesdays", "Thursdays", "Fridays", "Saturdays", "Sundays"]

    private static func ordinal(_ n: Int) -> String {
        let s = n % 10 == 1 && n != 11 ? "st" : n % 10 == 2 && n != 12 ? "nd" : n % 10 == 3 && n != 13 ? "rd" : "th"
        return "\(n)\(s)"
    }

    /// "Spending · food and drink · at Starbucks · Sep 1 – Sep 30, 2026 · personal".
    static func describe(_ t: DrillTarget) -> String {
        let d = t.drill
        var out = [d.flow == "income" ? "Income" : d.flow == "spending" ? (d.direction == "out" ? "Purchases" : "Spending") : "Income and spending"]
        if let k = d.incomeKind { out.append(k) }
        if let c = d.category { out.append(Category.label(c)) }
        if let x = d.detailed { out.append(Category.label(x, primary: d.category)) }
        if !d.notCategory.isEmpty { out.append("other categories") }
        if !d.notDetailed.isEmpty { out.append("other kinds") }
        if !d.notSource.isEmpty { out.append("other sources") }
        if let m = d.merchant { out.append("\(d.flow == "income" ? "from" : "at") \(m)") }
        if let w = d.weekday { out.append("on \(w >= 0 && w < weekdays.count ? weekdays[w] : "that weekday")") }
        if let day = d.day { out.append("on the \(ordinal(day))") }
        let from = d.from ?? t.slice.from, to = d.to ?? t.slice.to
        out.append("\(Fmt.date(from, year: from.prefix(4) != to.prefix(4))) – \(Fmt.date(to, year: true))")
        if t.slice.scope == "personal" || t.slice.scope == "business" { out.append(t.slice.scope) }
        return out.joined(separator: " · ")
    }

    /// What the total is: income, spending (purchases), or the net of both.
    static func totalLabel(_ d: Drill) -> String {
        d.flow == "income" ? "income" : d.flow == "spending" ? (d.direction == "out" ? "purchases" : "spending") : "net"
    }
}

/// The transactions behind an Insights number, adding up to it: posted, without
/// transfers between your accounts or card payments, grouped as Insights grouped
/// them (docs/80 "GET /transactions"). Newest or largest first.
struct DrillScreen: View {
    @Environment(AppModel.self) private var model
    let target: DrillTarget
    @State private var sort: String
    @State private var rows: [Txn] = []
    @State private var total = 0
    @State private var sum = 0.0
    @State private var page = 1
    @State private var loading = false
    @State private var error: String?
    @State private var loaded = false

    init(target: DrillTarget) {
        self.target = target
        _sort = State(initialValue: target.drill.largestFirst ? "largest" : "newest")
    }

    private func query(page: Int) -> TxnQuery {
        TxnQuery(from: target.slice.from, to: target.slice.to, sort: sort, drill: target.drill,
                 scope: target.slice.scope, page: page, pageSize: 50)
    }

    var body: some View {
        Screen(target.title) {
            Panel("from insights") {
                VStack(alignment: .leading, spacing: 8) {
                    Text(DrillWords.describe(target)).font(JFFont.sans(14)).foregroundStyle(JF.ink)
                        .fixedSize(horizontal: false, vertical: true)
                    if let why = target.drill.why.flatMap({ DrillWords.why[$0] }) {
                        Text(why).font(JFFont.sans(13)).foregroundStyle(JF.ink2).fixedSize(horizontal: false, vertical: true)
                    }
                    if loaded {
                        HStack(spacing: 6) {
                            Fine("\(total) transaction\(total == 1 ? "" : "s") · \(DrillWords.totalLabel(target.drill))")
                            // Plaid's sign: spending sums positive; income and the net read the other way.
                            if target.drill.flow == "all" {
                                MoneyText(-sum, style: .signed, size: 12, weight: .medium)
                            } else {
                                MoneyText(target.drill.flow == "spending" ? sum : -sum, size: 12, weight: .medium)
                            }
                        }
                    }
                }
            }
            Panel("transactions", flush: true, actions: {
                Chips(options: [("newest", "newest"), ("largest", "largest")], value: $sort)
            }) {
                VStack(spacing: 0) {
                    if let error, rows.isEmpty { ErrorNote(error) { Task { await reload() } }.padding(16) }
                    if loading && rows.isEmpty { Skeleton(height: 240).padding(16) }
                    if loaded && rows.isEmpty && error == nil { Fine("None in this range.").padding(16) }
                    RuledList(rows) { tx in
                        NavigationLink { TxnDetailScreen(tx: tx) } label: { TxnRow(tx: tx, showDate: true) }
                            .buttonStyle(.plain)
                    }
                    if rows.count < total {
                        Button(loading ? "Loading…" : "More") { Task { await more() } }
                            .font(JFFont.mono(12, .medium))
                            .padding(16)
                            .disabled(loading)
                    }
                }
            }
        }
        .navigationBarTitleDisplayMode(.inline)
        .task(id: TaskKey(sort: sort, token: model.refreshToken)) { await reload() }
    }

    private struct TaskKey: Hashable { let sort: String; let token: UUID }

    private func reload() async {
        loading = true
        defer { loading = false }
        do {
            let r = try await APIClient.shared.transactions(query(page: 1))
            rows = r.transactions
            total = r.total
            sum = r.sum
            page = 1
            error = nil
            loaded = true
        } catch is CancellationError {
        } catch let e as APIError {
            model.handle(e)
            error = e.errorDescription
        } catch {}
    }

    private func more() async {
        guard !loading, rows.count < total else { return }
        loading = true
        defer { loading = false }
        if let r = try? await APIClient.shared.transactions(query(page: page + 1)) {
            page += 1
            let seen = Set(rows.map(\.id))
            rows += r.transactions.filter { !seen.contains($0.id) }
        }
    }
}
