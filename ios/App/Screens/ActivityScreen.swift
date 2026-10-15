import JFinancesKit
import SwiftUI

/// The Activity tab: on a phone the list pushes a transaction; on a wide screen
/// (an iPad, the open iPhone Duo) it opens beside the list. The open one lives
/// in the model, so folding or unfolding a Duo keeps it.
struct ActivityTab: View {
    @Environment(AppModel.self) private var model
    @Environment(\.horizontalSizeClass) private var sizeClass

    var body: some View {
        @Bindable var model = model
        if sizeClass == .regular {
            TwoPane {
                NavigationStack { ActivityScreen(picking: true) }
            } detail: {
                NavigationStack {
                    if let tx = model.selectedTxn {
                        TxnDetailScreen(tx: tx).id(tx.id)
                    } else {
                        PickPrompt("Pick a transaction to see it in full or change its category.")
                    }
                }
            }
        } else {
            NavigationStack {
                ActivityScreen()
                    .navigationDestination(item: $model.selectedTxn) { TxnDetailScreen(tx: $0) }
            }
        }
    }
}

/// Every transaction, newest first by day (or largest first): search, filter by
/// account or category, and scroll for more.
struct ActivityScreen: View {
    @Environment(AppModel.self) private var model
    /// Wide screens: the open transaction is marked in the list.
    var picking = false
    @State private var search = ""
    @State private var accountId: String?
    @State private var category: String?
    /// newest | largest: biggest amounts first, either way.
    @State private var sort = "newest"
    @State private var rows: [Txn] = []
    @State private var total = 0
    @State private var page = 1
    @State private var loading = false
    @State private var error: String?
    @State private var accounts: [Account] = []
    @State private var categories: [String] = []

    private struct Key: Hashable { let q: String; let a: String?; let c: String?; let s: String; let t: UUID }

    var body: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 0, pinnedViews: [.sectionHeaders]) {
                TabTitle("Activity").padding(.horizontal, JF.gutter).padding(.top, 4)
                SearchField(text: $search, prompt: "Merchant, name, or note")
                    .padding(.horizontal, JF.gutter).padding(.top, 10).padding(.bottom, 10)
                filters.padding(.horizontal, JF.gutter).padding(.bottom, 10)
                if let error, rows.isEmpty { ErrorNote(error) { Task { await reload() } }.padding(.horizontal, JF.gutter) }
                if sort == "largest" && !rows.isEmpty {
                    // Largest first: one list, each row with its date.
                    VStack(spacing: 0) {
                        ForEach(Array(rows.enumerated()), id: \.element.id) { i, tx in
                            Button { model.selectedTxn = tx } label: { TxnRow(tx: tx, showDate: true) }
                                .buttonStyle(.plain)
                                .picked(picking && model.selectedTxn?.id == tx.id)
                                .padding(.horizontal, 16)
                                .onAppear { if tx.id == rows.last?.id { Task { await more() } } }
                            if i < rows.count - 1 { Rule().padding(.leading, 58) }
                        }
                    }
                    .background(JF.panel)
                    .overlay(Rectangle().strokeBorder(JF.line, lineWidth: 1))
                    .padding(.horizontal, JF.gutter)
                    .padding(.bottom, 12)
                }
                ForEach(sort == "largest" ? [] : days, id: \.0) { day, txs in
                    Section {
                        VStack(spacing: 0) {
                            ForEach(Array(txs.enumerated()), id: \.element.id) { i, tx in
                                Button { model.selectedTxn = tx } label: { TxnRow(tx: tx) }
                                    .buttonStyle(.plain)
                                    .picked(picking && model.selectedTxn?.id == tx.id)
                                    .padding(.horizontal, 16)
                                    .onAppear { if tx.id == rows.last?.id { Task { await more() } } }
                                if i < txs.count - 1 { Rule().padding(.leading, 58) }
                            }
                        }
                        .background(JF.panel)
                        .overlay(Rectangle().strokeBorder(JF.line, lineWidth: 1))
                        .padding(.horizontal, JF.gutter)
                        .padding(.bottom, 12)
                    } header: {
                        HStack {
                            Text(Fmt.dayHeading(day)).font(JFFont.mono(12, .medium)).foregroundStyle(JF.ink2)
                            Spacer()
                            let out = txs.filter { $0.amount > 0 }.reduce(0) { $0 + $1.amount }
                            if out > 0 { MoneyText(out, cents: false, size: 11).foregroundStyle(JF.ink3) }
                        }
                        .padding(.horizontal, JF.gutter)
                        .padding(.vertical, 6)
                        .background(JF.page)
                    }
                }
                if loading && rows.isEmpty { Skeleton(height: 300).padding(.horizontal, JF.gutter) }
                if !loading && rows.isEmpty && error == nil {
                    Fine("No transactions match.").frame(maxWidth: .infinity).padding(.top, 40)
                }
                if loading && !rows.isEmpty { ProgressView().frame(maxWidth: .infinity).padding() }
                if !rows.isEmpty && rows.count >= total {
                    Fine("\(total) transactions").frame(maxWidth: .infinity).padding(.vertical, 16)
                }
            }
            .padding(.vertical, 8)
        }
        .scrollIndicators(.hidden)
        .background(JF.page)
        .navigationTitle("Activity")
        .toolbar(.hidden, for: .navigationBar)
        .statusBarBackdrop()
        .refreshable { await model.pullToRefresh() }
        .task(id: Key(q: search, a: accountId, c: category, s: sort, t: model.refreshToken)) {
            if !search.isEmpty { try? await Task.sleep(for: .milliseconds(300)) }
            if Task.isCancelled { return }
            await reload()
        }
        .task {
            // An offline account holds what its statements imported; homes and cars hold none.
            accounts = (try? await APIClient.shared.accounts())?.filter { $0.is_hidden != true && $0.holdsTransactions } ?? []
            categories = (try? await APIClient.shared.categories()) ?? []
        }
    }

    private var days: [(String, [Txn])] {
        var order: [String] = []
        var groups: [String: [Txn]] = [:]
        for t in rows {
            let d = String(t.date.prefix(10))
            if groups[d] == nil { order.append(d) }
            groups[d, default: []].append(t)
        }
        return order.map { ($0, groups[$0]!) }
    }

    /// The account filter's sections, in the Accounts tab's order (Cash, Investments,
    /// Credit cards, Loans…), an institution's accounts together.
    private var accountGroups: [(String, [Account])] {
        Account.groupOrder.compactMap { key in
            let list = accounts.filter { $0.groupKey == key }
                .sorted { ($0.institution_name ?? "", $0.name) < ($1.institution_name ?? "", $1.name) }
            return list.isEmpty ? nil : (Account.groupLabels[key] ?? key, list)
        }
    }

    private var filters: some View {
        FlowLayout(spacing: 8) {
            Menu {
                Button("All accounts") { accountId = nil }
                ForEach(accountGroups, id: \.0) { label, list in
                    Section(label) {
                        ForEach(list) { a in Button(a.filterLabel) { accountId = a.id } }
                    }
                }
            } label: {
                FilterChip(text: accounts.first { $0.id == accountId }?.name ?? "all accounts", active: accountId != nil)
            }
            Menu {
                Button("All categories") { category = nil }
                ForEach(categories, id: \.self) { c in Button(Category.label(c)) { category = c } }
            } label: {
                FilterChip(text: category.map { Category.label($0) } ?? "all categories", active: category != nil)
            }
            Menu {
                Picker("Order", selection: $sort) {
                    Text("Newest first").tag("newest")
                    Text("Largest first").tag("largest")
                }
            } label: {
                FilterChip(text: sort == "largest" ? "largest first" : "newest first", active: sort == "largest")
            }
        }
    }

    private func reload() async {
        loading = true
        defer { loading = false }
        page = 1
        do {
            let r = try await APIClient.shared.transactions(TxnQuery(q: search, accountId: accountId, category: category, sort: sort, page: 1))
            rows = r.transactions
            total = r.total
            error = nil
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
        let next = page + 1
        if let r = try? await APIClient.shared.transactions(TxnQuery(q: search, accountId: accountId, category: category, sort: sort, page: next)) {
            page = next
            let seen = Set(rows.map(\.id))
            rows += r.transactions.filter { !seen.contains($0.id) }
            total = r.total
        }
    }
}

/// The search field under the title, where the navigation bar's search drawer was.
struct SearchField: View {
    @Binding var text: String
    let prompt: String

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: "magnifyingglass").foregroundStyle(JF.ink3)
            TextField(prompt, text: $text)
                .font(JFFont.sans(16))
                .foregroundStyle(JF.ink)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()
                .submitLabel(.search)
            if !text.isEmpty {
                Button { text = "" } label: { Image(systemName: "xmark.circle.fill").foregroundStyle(JF.ink3) }
                    .accessibilityLabel("Clear search")
            }
        }
        .padding(.horizontal, 12)
        .frame(height: 40)
        .background(JF.panel2, in: RoundedRectangle(cornerRadius: 10))
    }
}

struct FilterChip: View {
    let text: String
    let active: Bool

    var body: some View {
        HStack(spacing: 6) {
            Text(text).font(JFFont.mono(12, .medium)).lineLimit(1)
            Image(systemName: "chevron.down").font(.system(size: 9, weight: .bold))
        }
        .foregroundStyle(active ? JF.accentInk : JF.ink2)
        .padding(.horizontal, 10)
        .frame(height: 30)
        .background(active ? JF.accent : JF.panel)
        .overlay(Rectangle().strokeBorder(active ? JF.accent : JF.line, lineWidth: 1))
    }
}

/// One transaction in full, including which account it belongs to; Edit changes
/// its category, note and whether it counts as business.
struct TxnDetailScreen: View {
    @State private var tx: Txn
    @State private var editing = false
    @State private var toast: String?

    init(tx: Txn) {
        _tx = State(initialValue: tx)
    }

    var body: some View {
        Screen(tx.title, inline: true) {
            detail
        }
        .toolbar { ToolbarItem(placement: .topBarTrailing) { Button("Edit") { editing = true } } }
        .toast($toast)
        .sheet(isPresented: $editing) {
            TxnEditSheet(tx: tx) { tx = $0; toast = "Saved" }
        }
    }

    @ViewBuilder private var detail: some View {
            Panel(tx.pending ? "pending" : "posted") {
                VStack(alignment: .leading, spacing: 10) {
                    Readout(tx.amount < 0 ? "money in" : "money out",
                            value: Fmt.money(abs(tx.amount), currency: tx.currency), size: 40)
                    Text(Fmt.day(tx.date)?.formatted(.dateTime.weekday(.wide).month(.wide).day().year()) ?? tx.date)
                        .font(JFFont.mono(12)).foregroundStyle(JF.ink3)
                }
            }
            Panel("details") {
                VStack(spacing: 0) {
                    KeyValueRow("merchant") { Text(tx.merchant_name ?? "—") }
                    KeyValueRow("description") { Text(tx.name) }
                    KeyValueRow("category") { Text(Category.label(tx.category)) }
                    if let d = tx.category_detailed { KeyValueRow("bank category") { Text(Category.label(d, primary: tx.category_primary)) } }
                    if tx.is_business == true || tx.business != nil {
                        // Business by its own flag, else its account's; "marked" when the person said so.
                        KeyValueRow("use") {
                            HStack(spacing: 6) {
                                if tx.is_business == true { BusinessMark() }
                                Text(tx.is_business == true ? "business" : "personal")
                                if tx.business != nil { Text("marked").font(JFFont.mono(11)).foregroundStyle(JF.ink3) }
                            }
                        }
                    }
                    if let ch = tx.payment_channel { KeyValueRow("channel") { Text(ch) } }
                    if let a = tx.authorized_date, a != tx.date { KeyValueRow("authorized") { Text(Fmt.date(a, year: true)) } }
                    if let n = tx.notes, !n.isEmpty { KeyValueRow("note") { Text(n) } }
                }
            }
            Panel("account") {
                VStack(spacing: 0) {
                    KeyValueRow("account") { Text(tx.account_name ?? "—") }
                    if let inst = tx.institution_name { KeyValueRow("institution") { Text(inst) } }
                    if let m = tx.account_mask { KeyValueRow("number") { Text("··\(m)").font(JFFont.mono(14)) } }
                }
            }
    }
}
