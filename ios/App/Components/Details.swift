import JFinancesKit
import SwiftUI

// An account's details (GET /accounts/{id}/details) and an offline home's or
// car's market value (GET /accounts/{id}/asset), as the dashboard's account
// panel shows them. Read-only: what the bank doesn't report is entered on the
// dashboard, and the phone says so.

extension View {
    /// `figure(size:)` only when `on`: a word next to a figure stays readable.
    @ViewBuilder func figure(if on: Bool, size: CGFloat) -> some View {
        if on { figure(size: size) } else { self }
    }
}

/// Where a value came from, when it wasn't the bank: entered, or worked out from the others.
struct SourceTag: View {
    let source: String?

    var body: some View {
        if source == "you" {
            Text("entered").font(JFFont.mono(10)).foregroundStyle(JF.accentText)
                .padding(.horizontal, 4).frame(height: 16)
                .overlay(Rectangle().strokeBorder(JF.accent.opacity(0.45), lineWidth: 1))
                .fixedSize()
        } else if source == "calc" {
            Text("calc").font(JFFont.mono(10)).foregroundStyle(JF.ink3)
                .padding(.horizontal, 4).frame(height: 16)
                .overlay(Rectangle().strokeBorder(JF.line, style: StrokeStyle(lineWidth: 1, dash: [3, 2])))
                .fixedSize()
        }
    }
}

enum FactFormat {
    private static func ordinal(_ n: Int) -> String {
        let s = ["th", "st", "nd", "rd"], v = n % 100
        let i = (v - 20) % 10
        let suffix = (i > 0 && i < 4) ? s[i] : (v > 0 && v < 4) ? s[v] : s[0]
        return "\(n)\(suffix)"
    }

    /// 297 -> "297 months · 24 yr 9 mo".
    static func months(_ n: Int) -> String {
        let y = n / 12, m = n % 12
        if n < 12 { return "\(n) month\(n == 1 ? "" : "s")" }
        return "\(n) months · " + (m > 0 ? "\(y) yr \(m) mo" : "\(y) year\(y == 1 ? "" : "s")")
    }

    /// "6.125" stays "6.125"; 5.0 becomes "5".
    static func plain(_ v: JSONValue) -> String {
        if case .string(let s) = v { return s }
        guard let d = v.number else { return "—" }
        var s = String(format: "%.4f", d)
        while s.hasSuffix("0") { s.removeLast() }
        if s.hasSuffix(".") { s.removeLast() }
        return s
    }

    static func isFigure(_ format: String) -> Bool {
        ["money", "money0", "pct", "ratio", "count"].contains(format)
    }

    static func text(_ f: DetailFact) -> String {
        guard let v = f.value else { return "—" }
        switch f.format {
        case "money": return Fmt.money(v.number ?? 0)
        case "money0": return Fmt.money(v.number ?? 0, cents: false)
        case "pct": return "\(plain(v))%"
        case "ratio": return "\(Int(((v.number ?? 0) * 100).rounded()))%"
        case "date": return Fmt.date(v.string, year: true)
        case "months": return months(Int(v.number ?? 0))
        case "day": return "the \(ordinal(Int(v.number ?? 0)))"
        case "count": return plain(v)
        case "bool":
            if case .bool(let b) = v { return b ? "yes" : "no" }
            return plain(v)
        default:
            if case .string(let s) = v { return s }
            return plain(v)
        }
    }
}

/// One fact's value: the figure (blurred with the switch), its note, and where it came from.
struct FactValue: View {
    let fact: DetailFact
    let tag: Bool

    var body: some View {
        VStack(alignment: .trailing, spacing: 2) {
            HStack(spacing: 6) {
                Text(FactFormat.text(fact))
                    .font(FactFormat.isFigure(fact.format) ? JFFont.mono(14) : JFFont.sans(14))
                    .figure(if: FactFormat.isFigure(fact.format), size: 14)
                if tag { SourceTag(source: fact.source) }
            }
            if let note = fact.note, !note.isEmpty {
                // A note can carry figures ("$592.38 to principal"): those blur too.
                Text(note).font(JFFont.mono(11)).foregroundStyle(JF.ink3)
                    .figure(if: note.contains(where: \.isNumber), size: 11)
            }
        }
    }
}

/// The account's details, one panel per section, as the dashboard's account panel.
struct AccountDetailsPanels: View {
    let accountId: String

    var body: some View {
        Loader(height: 160) {
            try await APIClient.shared.accountDetails(id: accountId)
        } content: { d in
            VStack(alignment: .leading, spacing: 12) {
                ForEach(d.sections.filter { s in s.facts.contains(where: \.isKnown) }) { s in
                    // A section that is all worked out (its note says so) doesn't tag every row.
                    let tags = s.facts.contains { $0.isKnown && $0.source != "calc" }
                    Panel(s.title) {
                        VStack(alignment: .leading, spacing: 0) {
                            if let note = s.note, !note.isEmpty {
                                Text(note).font(JFFont.sans(13)).foregroundStyle(JF.ink2).padding(.bottom, 4)
                            }
                            ForEach(s.facts.filter(\.isKnown)) { f in
                                KeyValueRow(f.label) { FactValue(fact: f, tag: tags) }
                            }
                        }
                    }
                }
                if d.missing > 0 {
                    Fine("\(d.missing) detail\(d.missing == 1 ? "" : "s") the bank doesn't report can be added on the dashboard: Accounts → this account → Add details.")
                }
            }
        }
    }
}

/// An offline home's or car's market value: the latest monthly estimate, what it
/// was based on, and when the next one comes. Estimates arrive once a month on
/// their own; nothing here asks for one.
struct MarketValuePanel: View {
    let account: Account

    private static let needs = [
        "address": "its street address", "city": "its city", "state": "its state", "zip": "its ZIP",
        "vin": "its VIN", "mileage": "its mileage", "location": "where it's kept",
    ]

    private static func monthName(_ iso: String) -> String {
        Fmt.day(iso)?.formatted(.dateTime.month(.wide).year().locale(Locale(identifier: "en_US"))) ?? iso
    }

    private struct Loaded {
        let info: AssetInfo
        let accounts: [Account]
    }

    var body: some View {
        Loader(height: 120) {
            async let info = APIClient.shared.asset(id: account.id)
            async let accounts = APIClient.shared.accounts()
            return Loaded(info: try await info, accounts: (try? await accounts) ?? [])
        } content: { loaded in
            if let kind = loaded.info.kind {
                panel(kind, loaded.info, loaded.accounts)
            }
        }
    }

    private func panel(_ kind: String, _ info: AssetInfo, _ accounts: [Account]) -> some View {
        let last = info.valuations.first { $0.status == "ok" && $0.value != nil }
        let latest = info.valuations.first
        let det = info.details
        let on = info.valuation_enabled != false
        let home = det?.garage_account_id.flatMap { id in accounts.first { $0.id == id } }
        return Panel("market value") {
            VStack(alignment: .leading, spacing: 8) {
                if !on {
                    Fine("Kept by hand: market values are off for it.")
                } else if !info.missing.isEmpty {
                    Fine("Needs \(info.missing.map { Self.needs[$0] ?? $0 }.joined(separator: ", ")) to be valued from market data once a month. Add \(info.missing.count == 1 ? "it" : "them") on the dashboard.")
                } else if let next = info.next_month {
                    Fine("Valued from market data once a month; the next estimate comes in \(Self.monthName(next)).")
                }
                if let l = latest, l.status != "ok", l.status != "pending" {
                    let what = l.status == "skipped" ? "held back (the month's requests were used up)"
                        : l.status == "no_value" ? "no estimate for it" : "the estimate didn't come through"
                    Fine("\(Self.monthName(l.month)): \(what)\(l.error.map { " (\($0))" } ?? ""); it's asked again next month.")
                }
                VStack(spacing: 0) {
                    if let last, let value = last.value {
                        KeyValueRow("estimate") {
                            VStack(alignment: .trailing, spacing: 2) {
                                MoneyText(value, cents: false)
                                if let lo = last.low, let hi = last.high {
                                    Text("\(Fmt.money(lo, cents: false)) – \(Fmt.money(hi, cents: false))")
                                        .font(JFFont.mono(11)).foregroundStyle(JF.ink3).figure(size: 11)
                                }
                            }
                        }
                        KeyValueRow("as of") { Text(Fmt.date(last.as_of, year: true)) }
                        KeyValueRow("based on") { Text(basis(kind, last)).figure(if: kind != "home", size: 14) }
                    }
                    if kind == "vehicle", let det {
                        if let label = det.vehicle_label { KeyValueRow("vehicle") { Text(label) } }
                        if let miles = det.mileage {
                            KeyValueRow("mileage") {
                                VStack(alignment: .trailing, spacing: 2) {
                                    Text("\(Fmt.number(info.projected_miles ?? miles)) now").font(JFFont.mono(14)).figure(size: 14)
                                    Text("\(Fmt.number(miles)) on \(Fmt.date(det.mileage_as_of, year: true)), \(Fmt.number(det.miles_per_month ?? 1000)) a month")
                                        .font(JFFont.mono(11)).foregroundStyle(JF.ink3).figure(size: 11)
                                }
                            }
                        }
                        if let home {
                            KeyValueRow("kept at") { Text(home.name) }
                        } else if let zip = info.priced_at_zip {
                            KeyValueRow("kept at") { Text("ZIP \(zip)") }
                        }
                    }
                    if kind == "home", let det, let line = det.address_line, !line.isEmpty {
                        let place = [det.city, det.state].compactMap { $0 }.filter { !$0.isEmpty }.joined(separator: ", ")
                        KeyValueRow("address") {
                            Text([line, place, det.zip ?? ""].filter { !$0.isEmpty }.joined(separator: " · "))
                        }
                    }
                }
            }
        }
    }

    private func basis(_ kind: String, _ v: AssetValuation) -> String {
        if kind == "home" {
            let comps = v.detail?["comparables"]?.number.map { Int($0) }
            return comps.map { "\($0) comparable sales near the address" } ?? "comparable sales near the address"
        }
        if let miles = v.inputs?["miles"]?.number { return "what a dealer would ask, at \(Fmt.number(miles)) miles" }
        return "what a dealer would ask"
    }
}
