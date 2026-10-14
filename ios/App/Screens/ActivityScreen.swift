import JFinancesKit
import SwiftUI

/// Every transaction, newest first, by day: search, filter by account or
/// category, and scroll for more.
struct ActivityScreen: View {
    @Environment(AppModel.self) private var model
    @State private var search = ""
    @State private var accountId: String?
    @State private var category: String?
    @State private var rows: [Txn] = []
    @State private var total = 0
    @State private var page = 1
    @State private var loading = false
    @State private var error: String?
    @State private var accounts: [Account] = []
    @State private var categories: [String] = []

    private struct Key: Hashable { let q: String; let a: String?; let c: String?; let t: UUID }

    var body: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 0, pinnedViews: [.sectionHeaders]) {
                filters.padding(.horizontal, JF.gutter).padding(.bottom, 10)
                if let error, rows.isEmpty { ErrorNote(error) { Task { await reload() } }.padding(.horizontal, JF.gutter) }
                ForEach(days, id: \.0) { day, txs in
                    Section {
                        VStack(spacing: 0) {
                            ForEach(Array(txs.enumerated()), id: \.element.id) { i, tx in
                                NavigationLink { TxnDetailScreen(tx: tx) } label: { TxnRow(tx: tx) }
                                    .buttonStyle(.plain)
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
        .searchable(text: $search, placement: .navigationBarDrawer(displayMode: .always), prompt: "Merchant, name, or note")
        .toolbar { ToolbarItem(placement: .topBarTrailing) { BlurButton() } }
        .refreshable { await model.pullToRefresh() }
        .task(id: Key(q: search, a: accountId, c: category, t: model.refreshToken)) {
            if !search.isEmpty { try? await Task.sleep(for: .milliseconds(300)) }
            if Task.isCancelled { return }
            await reload()
        }
        .task {
            accounts = (try? await APIClient.shared.accounts())?.filter { $0.is_hidden != true && !$0.isManual } ?? []
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

    private var filters: some View {
        HStack(spacing: 8) {
            Menu {
                Button("All accounts") { accountId = nil }
                ForEach(accounts) { a in
                    Button("\(a.institution_name.map { $0 + ": " } ?? "")\(a.name)\(a.mask.map { " ··\($0)" } ?? "")") { accountId = a.id }
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
            Spacer(minLength: 0)
        }
    }

    private func reload() async {
        loading = true
        defer { loading = false }
        page = 1
        do {
            let r = try await APIClient.shared.transactions(TxnQuery(q: search, accountId: accountId, category: category, page: 1))
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
        if let r = try? await APIClient.shared.transactions(TxnQuery(q: search, accountId: accountId, category: category, page: next)) {
            page = next
            let seen = Set(rows.map(\.id))
            rows += r.transactions.filter { !seen.contains($0.id) }
            total = r.total
        }
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

/// One transaction in full, including which account it belongs to.
struct TxnDetailScreen: View {
    let tx: Txn

    var body: some View {
        Screen(tx.title) {
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
        .navigationBarTitleDisplayMode(.inline)
    }
}
