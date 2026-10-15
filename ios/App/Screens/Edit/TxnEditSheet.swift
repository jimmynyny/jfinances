import JFinancesKit
import SwiftUI

/// One transaction's category, note and whether it counts as business, as the
/// dashboard's transaction drawer edits them (PATCH /transactions/{id}). A new
/// category typed here is kept in the bank's style (HOME_REPAIRS) and one that
/// reads like an existing one is that one, so names never split.
struct TxnEditSheet: View {
    let tx: Txn
    let onSaved: (Txn) -> Void
    @State private var categories: [String] = []
    /// The chosen category key; "" is the bank's own.
    @State private var pick: String
    @State private var typed = ""
    @State private var notes: String
    /// account | business | personal
    @State private var business: String

    init(tx: Txn, onSaved: @escaping (Txn) -> Void) {
        self.tx = tx
        self.onSaved = onSaved
        _pick = State(initialValue: tx.user_category ?? "")
        _notes = State(initialValue: tx.notes ?? "")
        _business = State(initialValue: tx.business == true ? "business" : tx.business == false ? "personal" : "account")
    }

    private static func words(_ c: String) -> String { c.lowercased().replacingOccurrences(of: "_", with: " ").trimmingCharacters(in: .whitespaces) }

    /// The category to send: nil keeps it, `.null` goes back to the bank's.
    private var resolved: (value: JSONValue?, isNew: Bool) {
        let t = typed.trimmingCharacters(in: .whitespaces).replacingOccurrences(of: "\\s+", with: " ", options: .regularExpression)
        if !t.isEmpty {
            if let same = categories.first(where: { Self.words($0) == Self.words(t) }) { return (.string(same), false) }
            return (.string(t.uppercased().replacingOccurrences(of: " ", with: "_")), true)
        }
        return (pick.isEmpty ? .null : .string(pick), false)
    }

    private var current: String {
        if !typed.trimmingCharacters(in: .whitespaces).isEmpty { return "new: " + Self.words(typed) }
        return pick.isEmpty ? "the bank's (\(Category.label(tx.category_primary)))" : Category.label(pick)
    }

    private var options: [String] {
        var seen = Set<String>()
        return categories.sorted { Self.words($0) < Self.words($1) }.filter { seen.insert(Self.words($0)).inserted }
    }

    var body: some View {
        FormSheet(title: tx.title, save: save) {
            Panel("category") {
                VStack(alignment: .leading, spacing: 12) {
                    MenuField(label: "category", current: current) {
                        Button("the bank's (\(Category.label(tx.category_primary)))") { pick = ""; typed = "" }
                        ForEach(options, id: \.self) { c in Button(Category.label(c)) { pick = c; typed = "" } }
                    }
                    Field(label: "or a new category", text: $typed, placeholder: "e.g. home repairs",
                          help: typed.isEmpty ? nil : resolved.isNew ? "Adds “\(Self.words(typed))” as a new category." : "“\(Category.label(resolved.value.flatMap { if case .string(let s) = $0 { return s }; return nil }))” is already a category; it will be used.")
                    Fine("Filing this teaches a rule: new transactions from \(tx.title) on this account take the same category.")
                }
            }
            Panel("note") {
                Field(label: "note", text: $notes, placeholder: "Anything worth remembering")
            }
            Panel("use") {
                ChoiceField(label: "business or personal",
                            options: [("account", "account's (\(tx.is_business == true && tx.business == nil ? "business" : tx.business == nil ? "personal" : "as it is"))"),
                                      ("business", "business"), ("personal", "personal")],
                            value: $business,
                            help: "Business is kept out of personal Insights. \"Account's\" follows the account's own setting.")
            }
        }
        .task { categories = (try? await APIClient.shared.categories()) ?? [] }
    }

    private func save() async throws {
        var body = JSONBody()
        let (cat, _) = resolved
        if let cat, cat != (tx.user_category.map { JSONValue.string($0) } ?? .null) { body["user_category"] = cat }
        let note = notes.trimmingCharacters(in: .whitespacesAndNewlines)
        if note != (tx.notes ?? "") { body["notes"] = .text(note) }
        let flag: Bool? = business == "business" ? true : business == "personal" ? false : nil
        if flag != tx.business { body["business"] = .flag(flag) }
        guard !body.fields.isEmpty else { return }
        onSaved(try await APIClient.shared.patchTransaction(id: tx.id, body))
    }
}
