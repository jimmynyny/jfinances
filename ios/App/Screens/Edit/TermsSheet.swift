import JFinancesKit
import SwiftUI

/// What the bank doesn't report, filled in by hand: a loan's rate, term and
/// payment, a card's limit, a savings account's APY (PUT /accounts/{id}/terms).
/// As the person types, the server works out the rest (a preview that saves
/// nothing) and it shows below, as the dashboard's Add details form.
struct TermsSheet: View {
    let account: Account
    let details: AccountDetails
    let onSaved: (AccountDetails) -> Void
    @State private var values: [String: String]
    @State private var preview: AccountDetails?

    /// Common terms, one tap each.
    private static let picks: [String: [(Int, String)]] = [
        "mortgage": [(180, "15 yr"), (240, "20 yr"), (360, "30 yr")],
        "loan": [(36, "3 yr"), (48, "4 yr"), (60, "5 yr"), (72, "6 yr")],
        "student": [(120, "10 yr"), (240, "20 yr"), (300, "25 yr")],
    ]

    init(account: Account, details: AccountDetails, onSaved: @escaping (AccountDetails) -> Void) {
        self.account = account
        self.details = details
        self.onSaved = onSaved
        var v: [String: String] = [:]
        for f in details.editable {
            v[f.key] = Self.shown(details.terms?[f.key])
        }
        _values = State(initialValue: v)
    }

    private static func shown(_ v: JSONValue?) -> String {
        switch v {
        case .some(.string(let s)): return s
        case .some(.number(let d)): return d == d.rounded() ? String(Int(d)) : String(d)
        default: return ""
        }
    }

    private var editable: [DetailField] { details.editable }
    private var reported: [DetailField] { (details.fields ?? []).filter(\.isReported) }
    private var what: String { details.kind == "credit" ? "card issuer" : details.kind == "depository" ? "bank" : "lender" }

    /// The value as the API takes it, or what is wrong with it.
    private func parse(_ f: DetailField, _ raw: String) -> (value: JSONValue, error: String?) {
        let t = raw.trimmingCharacters(in: .whitespaces)
        if t.isEmpty { return (.null, nil) }
        switch f.format {
        case "date":
            guard t.range(of: #"^\d{4}-\d{2}-\d{2}$"#, options: .regularExpression) != nil else { return (.null, "a date, 2021-03-15") }
            if t > Fmt.isoDay(Date()) { return (.null, "not in the future") }
            return (.string(t), nil)
        case "choice":
            return (.string(t), nil)
        default:
            guard let n = Parse.number(t) else { return (.null, "a number") }
            let whole = f.format == "months" || f.format == "day"
            if whole, n != n.rounded() { return (.null, "a whole number") }
            if let lo = f.min, n < lo { return (.null, "at least \(Self.plain(lo))") }
            if let hi = f.max, n > hi { return (.null, "at most \(Fmt.number(hi))") }
            // Money and rates travel as the string typed, so the server's numeric keeps every digit.
            return (whole ? .number(n) : .string(t.replacingOccurrences(of: "[$,%\\s]", with: "", options: .regularExpression)), nil)
        }
    }

    private static func plain(_ d: Double) -> String { d == d.rounded() ? String(Int(d)) : String(d) }

    private var body_: JSONBody {
        var b = JSONBody()
        for f in editable { b[f.key] = parse(f, values[f.key] ?? "").value }
        return b
    }

    private var invalid: Bool { editable.contains { parse($0, values[$0.key] ?? "").error != nil } }
    private var bodyKey: String { editable.map { "\($0.key)=\(values[$0.key] ?? "")" }.joined(separator: "&") }

    var body: some View {
        FormSheet(title: "Details", canSave: !invalid, save: save) {
            Text("Fill in what the \(what) doesn't report. Leave anything you don't know blank: the rest is worked out from what you give.")
                .font(JFFont.sans(13)).foregroundStyle(JF.ink2)
            if !reported.isEmpty {
                Panel("from the \(what)") {
                    VStack(spacing: 0) {
                        ForEach(reported) { f in
                            KeyValueRow(f.label) { Text(FactFormat.text(DetailFact(key: f.key, label: f.label, value: f.bank, format: f.format, source: "bank", note: nil, field: nil))) }
                        }
                    }
                }
            }
            Panel("entered") {
                VStack(alignment: .leading, spacing: 14) {
                    ForEach(editable) { f in field(f) }
                }
            }
            if let p = preview {
                let shown = p.sections.filter { ["terms", "payoff", "card", "savings"].contains($0.key) && $0.facts.contains(where: \.isKnown) }
                ForEach(shown) { s in
                    Panel(s.title) {
                        VStack(alignment: .leading, spacing: 0) {
                            if let note = s.note, !note.isEmpty { Text(note).font(JFFont.sans(13)).foregroundStyle(JF.ink2).padding(.bottom, 4) }
                            ForEach(s.facts.filter(\.isKnown)) { f in KeyValueRow(f.label) { FactValue(fact: f, tag: true) } }
                        }
                    }
                }
            }
        }
        .task(id: bodyKey) {
            // Live preview, a beat after typing stops; invalid input keeps the last good one.
            guard !invalid else { return }
            try? await Task.sleep(for: .milliseconds(350))
            if Task.isCancelled { return }
            if let p = try? await APIClient.shared.previewTerms(id: account.id, body_) { preview = p }
        }
    }

    @ViewBuilder private func field(_ f: DetailField) -> some View {
        let raw = values[f.key] ?? ""
        let err = parse(f, raw).error
        let tip = details.suggestions?[f.key]
        if f.format == "choice" {
            ChoiceField(label: f.label, options: [("", "—")] + (f.options ?? []).map { ($0, $0) },
                        value: Binding(get: { values[f.key] ?? "" }, set: { values[f.key] = $0 }), help: f.help)
        } else {
            VStack(alignment: .leading, spacing: 6) {
                Field(label: f.format == "pct" ? "\(f.label) (%)" : f.label,
                      text: Binding(get: { values[f.key] ?? "" }, set: { values[f.key] = $0 }),
                      placeholder: f.format == "pct" ? "6.125" : f.format == "day" ? "15" : f.format == "months" ? "360" : f.format == "money" ? "0.00" : f.format == "date" ? "2021-03-15" : "",
                      mono: true,
                      keyboard: f.format == "date" ? .numbersAndPunctuation : f.format == "months" || f.format == "day" ? .numberPad : .decimalPad,
                      help: tip == nil ? f.help : nil, error: err)
                if f.format == "months", let picks = Self.picks[details.kind] {
                    HStack(spacing: 10) {
                        ForEach(picks, id: \.0) { n, label in
                            Button(label) { values[f.key] = String(n) }.font(JFFont.mono(12, .medium))
                        }
                    }
                }
                if let tip, raw.isEmpty {
                    HStack(alignment: .firstTextBaseline, spacing: 6) {
                        Button("use \(f.format == "day" ? "the \(FactFormat.text(DetailFact(key: f.key, label: f.label, value: tip.value, format: "day", source: nil, note: nil, field: nil)).dropFirst(4))" : FactFormat.text(DetailFact(key: f.key, label: f.label, value: tip.value, format: f.format, source: nil, note: nil, field: nil)))") {
                            values[f.key] = Self.shown(tip.value)
                        }
                        .font(JFFont.mono(12, .medium))
                        Fine(tip.why)
                    }
                }
            }
        }
    }

    private func save() async throws {
        onSaved(try await APIClient.shared.putTerms(id: account.id, body_))
    }
}
