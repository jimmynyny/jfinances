import JFinancesKit
import SwiftUI

/// An account's name, where it counts, whether it is hidden or business, and
/// (for a loan) the offline asset it is secured by, as the dashboard's Edit
/// drawer (PATCH /accounts/{id}). An offline account can also be removed here.
struct AccountEditSheet: View {
    let account: Account
    let onSaved: (Account) -> Void
    let onRemoved: () -> Void
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    @State private var name: String
    @State private var group: String
    @State private var hidden: Bool
    @State private var business: Bool
    @State private var securedBy: String
    @State private var all: [Account] = []

    private static let owned = ["cash", "investments", "real_estate", "vehicles", "other_assets"]
    private static let owed = ["credit_cards", "loans", "other_liabilities"]

    init(account: Account, onSaved: @escaping (Account) -> Void, onRemoved: @escaping () -> Void) {
        self.account = account
        self.onSaved = onSaved
        self.onRemoved = onRemoved
        _name = State(initialValue: account.name)
        _group = State(initialValue: account.groupKey)
        _hidden = State(initialValue: account.is_hidden ?? false)
        _business = State(initialValue: account.is_business ?? false)
        _securedBy = State(initialValue: account.secured_by_id ?? "")
    }

    private var natural: String { account.naturalGroupKey }
    private func label(_ k: String) -> String { (Account.groupLabels[k] ?? k) + (k == natural ? " (its type)" : "") }
    /// A loan, not a card: it can be secured by an offline home, car or other asset.
    private var isLoan: Bool { Self.owed.contains(group) && group != "credit_cards" }
    private var assets: [Account] {
        all.filter { $0.isManual && ["real_estate", "vehicle", "other_asset"].contains($0.manual_category ?? "") && $0.id != account.id }
    }

    private var groupHelp: String {
        if group == natural { return "Where it shows on Accounts and Overview and in net worth by kind." }
        let flip = Self.owed.contains(group) != Self.owed.contains(natural)
        return "Shows under \((Account.groupLabels[group] ?? group).lowercased()) instead of \((Account.groupLabels[natural] ?? natural).lowercased())"
            + (flip ? ", counted as \(Self.owed.contains(group) ? "owed" : "owned")." : ".")
    }

    var body: some View {
        FormSheet(title: "Edit account", canSave: !name.trimmingCharacters(in: .whitespaces).isEmpty, save: save) {
            Panel("name") {
                Field(label: "display name", text: $name, help: account.official_name)
            }
            Panel("counts as") {
                MenuField(label: "group", current: Account.groupLabels[group] ?? group, help: groupHelp) {
                    Section("Owned") { ForEach(Self.owned, id: \.self) { k in Button(label(k)) { group = k } } }
                    Section("Owed") { ForEach(Self.owed, id: \.self) { k in Button(label(k)) { group = k } } }
                }
                if isLoan {
                    MenuField(label: "secured by", current: assets.first { $0.id == securedBy }?.name ?? "nothing",
                              help: "The offline home, car or other asset this loan is against: its equity shows on the asset.") {
                        Button("nothing") { securedBy = "" }
                        ForEach(assets) { a in Button(a.name) { securedBy = a.id } }
                    }
                    .padding(.top, 12)
                }
            }
            Panel("visibility") {
                VStack(spacing: 12) {
                    ToggleRow(title: "Hide from overview and totals", on: $hidden)
                    ToggleRow(title: "Business account", help: "Kept out of personal Insights.", on: $business)
                }
            }
            Fine(account.isManual
                 ? "offline · \((account.manual_category ?? "").replacingOccurrences(of: "_", with: " "))"
                 : "\(account.institution_name ?? "connected") · \([account.type, account.subtype].compactMap { $0 }.joined(separator: " / "))")
            if account.isManual {
                DangerButton(title: "Remove this offline account", question: "Remove \(account.name)?",
                             message: "This deletes it and its value history from net worth. It cannot be undone.",
                             confirm: "Remove") {
                    do {
                        try await APIClient.shared.deleteAccount(id: account.id)
                        model.changed()
                        dismiss()
                        onRemoved()
                    } catch let e as APIError {
                        model.handle(e)
                    } catch {}
                }
            }
        }
        .task { all = (try? await APIClient.shared.accounts()) ?? [] }
    }

    private func save() async throws {
        var body = JSONBody()
        let n = name.trimmingCharacters(in: .whitespaces)
        if n != account.name { body["name"] = .string(n) }
        if hidden != (account.is_hidden ?? false) { body["is_hidden"] = .bool(hidden) }
        if business != (account.is_business ?? false) { body["is_business"] = .bool(business) }
        if group != account.groupKey { body["group"] = group == natural ? .null : .string(group) }
        if isLoan, securedBy != (account.secured_by_id ?? "") { body["secured_by_id"] = .text(securedBy) }
        guard !body.fields.isEmpty else { return }
        onSaved(try await APIClient.shared.patchAccount(id: account.id, body))
    }
}

/// An offline account's value today, or on a day: a new snapshot, as the
/// dashboard's "Update value" (PUT /accounts/{id}/value).
struct ValueSheet: View {
    let account: Account
    let onSaved: (Account) -> Void
    @State private var value: String
    @State private var asOf: Date?
    @State private var note = ""

    init(account: Account, onSaved: @escaping (Account) -> Void) {
        self.account = account
        self.onSaved = onSaved
        _value = State(initialValue: account.current_balance.map { String(format: "%.2f", $0) } ?? "")
    }

    private var parsed: Double? { Parse.money(value) }

    var body: some View {
        FormSheet(title: "Update value", canSave: parsed != nil, save: save) {
            Panel(account.name.lowercased()) {
                VStack(alignment: .leading, spacing: 12) {
                    Field(label: account.is_liability ? "owed now" : "value now", text: $value, placeholder: "0.00", mono: true,
                          keyboard: .decimalPad, help: account.is_liability ? "A positive amount owed." : nil,
                          error: value.isEmpty || parsed != nil ? nil : "a number")
                    DateField(label: "as of", date: $asOf, help: "Leave it for today. Back-dating rewrites that day's snapshot.")
                    Field(label: "note", text: $note, placeholder: "Zillow estimate, KBB…")
                }
            }
        }
    }

    private func save() async throws {
        guard let v = parsed else { return }
        onSaved(try await APIClient.shared.setValue(id: account.id, value: v, asOf: asOf.map(Fmt.isoDay), note: note))
    }
}
