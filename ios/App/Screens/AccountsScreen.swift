import JFinancesKit
import SwiftUI

/// The Accounts tab owns its navigation path so a widget's deep link can
/// push an account directly.
struct AccountsTab: View {
    @Environment(AppModel.self) private var model
    @State private var path: [Account] = []

    var body: some View {
        NavigationStack(path: $path) {
            AccountsScreen()
                .navigationDestination(for: Account.self) { AccountDetailScreen(account: $0) }
        }
        .task(id: model.pendingAccountId) { await openPending() }
    }

    private func openPending() async {
        guard let id = model.pendingAccountId else { return }
        model.pendingAccountId = nil
        let known = model.glance?.accounts.first { $0.id == id }
        if let known { path = [known]; return }
        if let all = try? await APIClient.shared.accounts(), let a = all.first(where: { $0.id == id }) { path = [a] }
    }
}

/// Every visible account by kind, with each group's total, as the dashboard's
/// Accounts page. Offline accounts are added at the bottom.
struct AccountsScreen: View {
    @State private var adding = false
    @State private var toast: String?

    var body: some View {
        Screen("Accounts") {
            Loader(height: 400) {
                try await APIClient.shared.overview()
            } content: { ov in
                VStack(spacing: 12) {
                    ForEach(ov.groups.filter { g in g.accounts.contains { $0.is_hidden != true } }) { g in
                        let accounts = g.accounts.filter { $0.is_hidden != true }
                        Panel(g.label.lowercased(), flush: true, actions: {
                            MoneyText(g.total, cents: false, size: 13, weight: .medium)
                        }) {
                            RuledList(accounts) { a in
                                NavigationLink(value: a) { AccountRow(account: a) }.buttonStyle(.plain)
                            }
                        }
                    }
                    if let at = ov.as_of { Fine("balances as of \(Fmt.relative(at))").frame(maxWidth: .infinity) }
                }
            }
            Button("Add an offline account") { adding = true }
                .buttonStyle(QuietButtonStyle())
        }
        .toast($toast)
        .sheet(isPresented: $adding) {
            AddOfflineSheet { a in toast = "Added \(a.name)" }
        }
    }
}

/// One account: its balance and line, a home's or car's market value,
/// everything known about it (the bank's facts, what was entered, what follows),
/// its holdings or its latest activity. Where it counts (its group), not its
/// type, decides which: an offline account counted as an investment shows
/// performance, one with imported statements its transactions. The Edit menu
/// changes what the dashboard's account drawer changes.
struct AccountDetailScreen: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    @State private var account: Account
    @State private var range = "6m"
    @State private var editing = false
    @State private var valuing = false
    @State private var terms: AccountDetails?
    @State private var asset: (AssetInfo?)?
    @State private var refreshing = false
    @State private var toast: String?

    init(account: Account) {
        _account = State(initialValue: account)
    }

    private var isInvestment: Bool { account.countsAsInvestment }
    private var isCredit: Bool { account.countsAsCard }

    var body: some View {
        Screen(account.name, inline: true) {
            screen
        }
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Menu {
                    Button("Edit account…", systemImage: "pencil") { editing = true }
                    if account.isManual {
                        Button("Update value…", systemImage: "dollarsign") { valuing = true }
                    } else {
                        Button("Refresh balance", systemImage: "arrow.clockwise") { Task { await refresh() } }
                    }
                } label: {
                    if refreshing { ProgressView() } else { Text("Edit") }
                }
            }
        }
        .toast($toast)
        .sheet(isPresented: $editing) {
            AccountEditSheet(account: account, onSaved: { account = $0; toast = "Saved" }, onRemoved: { dismiss() })
        }
        .sheet(isPresented: $valuing) {
            ValueSheet(account: account) { account = $0; toast = "Value updated" }
        }
        .sheet(item: Binding(get: { terms.map(TermsBox.init) }, set: { terms = $0?.details })) { box in
            TermsSheet(account: account, details: box.details) { _ in toast = "Details saved" }
        }
        .sheet(isPresented: Binding(get: { asset != nil }, set: { if !$0 { asset = nil } })) {
            AssetSheet(account: account, info: asset ?? nil) { _ in toast = "Market value details saved" }
        }
    }

    private struct TermsBox: Identifiable {
        let details: AccountDetails
        var id: String { details.kind }
    }

    private func refresh() async {
        refreshing = true
        defer { refreshing = false }
        do {
            account = try await APIClient.shared.refreshAccount(id: account.id)
            model.changed()
            toast = "Balance refreshed"
        } catch let e as APIError {
            model.handle(e)
            toast = e.errorDescription
        } catch {}
    }

    @ViewBuilder private var screen: some View {
            Panel(account.subtitle.isEmpty ? "balance" : account.subtitle.lowercased(), actions: {
                Chips(options: [("1m", "1m"), ("3m", "3m"), ("6m", "6m"), ("1y", "1y"), ("all", "all")], value: $range)
            }) {
                VStack(alignment: .leading, spacing: 14) {
                    Readout(account.is_liability ? "owed" : "balance",
                            value: Fmt.money(account.balance, cents: true, currency: account.currency), size: 40,
                            delta: account.change_1m.map { AnyView(Delta(amount: $0.amount, pct: $0.pct, label: "30 days", upIsGood: !account.is_liability)) })
                    Loader(id: range, height: 170) {
                        try await APIClient.shared.accountHistory(id: account.id, range: range)
                    } content: { pts in
                        if pts.count >= 2 {
                            TrendChart(points: pts.compactMap { p in Fmt.day(p.date).map { DatedValue(date: $0, value: p.balance) } },
                                       color: account.is_liability ? JF.divNeg : JF.accent, height: 170)
                        } else {
                            Fine("Not enough history yet.")
                        }
                    }
                    if isCredit, let limit = account.credit_limit, limit > 0 {
                        let used = account.balance / limit
                        VStack(alignment: .leading, spacing: 6) {
                            PixelMeter(ratio: used, cells: 32, tone: used >= 0.5 ? .neg : used >= 0.3 ? .warn : .accent)
                            HStack {
                                Fine("\(Fmt.pct(used, digits: 0)) of \(Fmt.money(limit, cents: false)) limit")
                                Spacer()
                                if let avail = account.available_balance {
                                    Fine("available")
                                    MoneyText(avail, cents: false, size: 11)
                                }
                            }
                        }
                    }
                }
            }

            if account.isValuedAsset { MarketValuePanel(account: account, onEdit: { asset = .some($0) }) }
            AccountDetailsPanels(accountId: account.id, onEdit: { terms = $0 })
            if isInvestment {
                PerformancePanel(accountId: account.id)
                HoldingsPanel(accountId: account.id)
            }
            if !isInvestment && account.holdsTransactions { AccountActivity(accountId: account.id) }
            about
    }

    private var kind: String {
        if account.isManual { return account.isValuedAsset ? "offline asset" : "offline, kept by hand" }
        return [account.type, account.subtype].compactMap { $0 }.joined(separator: " · ")
    }

    private var about: some View {
        Panel("about") {
            VStack(spacing: 0) {
                if let inst = account.institution_name { KeyValueRow("institution") { Text(inst) } }
                KeyValueRow("type") { Text(kind) }
                if account.group_override != nil, let label = Account.groupLabels[account.groupKey] {
                    KeyValueRow("counts as") { Text(label.lowercased()) }
                }
                if let m = account.mask { KeyValueRow("number") { Text("··\(m)").font(JFFont.mono(14)) } }
                if let official = account.official_name, official != account.name { KeyValueRow("bank's name") { Text(official) } }
                if account.is_business == true { KeyValueRow("use") { HStack(spacing: 6) { BusinessMark(); Text("business") } } }
                KeyValueRow("updated") { Text(Fmt.relative(account.balance_updated_at)).font(JFFont.mono(13)) }
            }
        }
    }
}

/// The latest transactions in one account, fifty at a time.
struct AccountActivity: View {
    let accountId: String
    @State private var rows: [Txn] = []
    @State private var total = 0
    @State private var page = 1
    @State private var loading = false

    var body: some View {
        Panel("activity", flush: true, actions: { if total > 0 { Fine("\(total) transactions") } }) {
            Loader(height: 200) {
                try await APIClient.shared.transactions(TxnQuery(accountId: accountId, page: 1, pageSize: 25))
            } content: { first in
                let shown = rows.isEmpty ? first.transactions : rows
                VStack(spacing: 0) {
                    if shown.isEmpty { Fine("No transactions.").padding(16) }
                    RuledList(shown) { tx in
                        NavigationLink { TxnDetailScreen(tx: tx) } label: { TxnRow(tx: tx, showAccount: false) }
                            .buttonStyle(.plain)
                    }
                    if shown.count < first.total {
                        Button(loading ? "Loading…" : "More") { Task { await more(first) } }
                            .font(JFFont.mono(12, .medium))
                            .padding(16)
                            .disabled(loading)
                    }
                }
                .onAppear { total = first.total }
            }
        }
    }

    private func more(_ first: TxnPage) async {
        loading = true
        defer { loading = false }
        if rows.isEmpty { rows = first.transactions }
        page += 1
        if let next = try? await APIClient.shared.transactions(TxnQuery(accountId: accountId, page: page, pageSize: 25)) {
            rows += next.transactions
        }
    }
}

/// Holdings in one account (or all of them, one row per security), largest first.
struct HoldingsPanel: View {
    var accountId: String?
    var limit = 15

    private struct Row: Identifiable {
        let id: String
        let ticker: String?
        let name: String?
        var quantity: Double
        var value: Double
        /// An offline account counted as an investment: its balance, no holdings.
        var keptByHand = false
    }

    private func merged(_ hs: [Holding]) -> [Row] {
        var out: [String: Row] = [:]
        for x in hs {
            let key = x.ticker ?? x.name ?? x.id
            if var r = out[key] {
                r.quantity += x.quantity
                r.value += x.value
                out[key] = r
            } else {
                out[key] = Row(id: key, ticker: x.ticker, name: x.name, quantity: x.quantity, value: x.value)
            }
        }
        return Array(out.values)
    }

    private func symbol(_ x: Row) -> String {
        guard let t = x.ticker else { return "—" }
        return t.hasPrefix("CUR:") ? "cash" : t
    }

    var body: some View {
        Loader(height: 160) {
            try await APIClient.shared.holdings()
        } content: { h in
            let accounts = h.accounts.filter { accountId == nil || $0.account.id == accountId }
            // An account with no holdings reported (one kept by hand) counts at its balance.
            let byHand = accounts.filter { $0.holdings.isEmpty && $0.account.isManual }.map {
                Row(id: $0.account.id, ticker: nil, name: $0.account.name, quantity: 0, value: $0.account.balance, keptByHand: true)
            }
            let all = (merged(accounts.flatMap(\.holdings)) + (accountId == nil ? byHand : [])).sorted { $0.value > $1.value }
            let total = all.reduce(0) { $0 + $1.value }
            Panel("holdings", flush: true, actions: { MoneyText(total, cents: false, size: 12, weight: .medium) }) {
                if all.isEmpty {
                    Fine(byHand.isEmpty
                         ? "No holdings reported."
                         : "An offline account: its value is what you set (or what its imported statements say). Holdings aren't listed.")
                        .padding(16)
                } else {
                    RuledList(Array(all.prefix(limit))) { x in
                        HStack(spacing: 12) {
                            Text(x.keptByHand ? "—" : symbol(x)).font(JFFont.mono(13, .semibold)).foregroundStyle(JF.ink).frame(width: 64, alignment: .leading)
                            VStack(alignment: .leading, spacing: 2) {
                                Text(x.name ?? "").font(JFFont.sans(13)).foregroundStyle(JF.ink2).lineLimit(1)
                                if x.keptByHand {
                                    Text("kept by hand").font(JFFont.mono(11)).foregroundStyle(JF.ink3)
                                } else {
                                    Text("\(Fmt.number(x.quantity, digits: x.quantity == x.quantity.rounded() ? 0 : 3)) sh").font(JFFont.mono(11)).foregroundStyle(JF.ink3).figure(size: 11)
                                }
                            }
                            Spacer(minLength: 8)
                            VStack(alignment: .trailing, spacing: 2) {
                                MoneyText(x.value, cents: false, size: 14, weight: .medium)
                                if total > 0 { Text(Fmt.pct(x.value / total, digits: 1)).font(JFFont.mono(11)).foregroundStyle(JF.ink3) }
                            }
                        }
                        .padding(.vertical, 8)
                    }
                    if all.count > limit { Fine("and \(all.count - limit) more").padding(16) }
                }
            }
        }
    }
}
