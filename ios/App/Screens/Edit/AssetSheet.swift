import JFinancesKit
import SwiftUI

/// What a monthly market value needs (docs/80 "Valuations"): a home's address,
/// or a car's VIN, mileage, how far it's driven a month and where it's kept
/// (one of the household's homes, whose ZIP prices it, or an address typed in).
/// Values are asked for once a month by the server; nothing here asks for one.
struct AssetDraft: Equatable {
    var enabled = true
    var addressLine = ""
    var city = ""
    var state = ""
    var zip = ""
    var propertyType = ""
    var bedrooms = ""
    var bathrooms = ""
    var squareFeet = ""
    var vin = ""
    var mileage = ""
    var milesPerMonth = 1000
    /// A home's id, `elsewhere` for an address typed in, or "" for nothing yet.
    var keptAt = ""

    static let elsewhere = "__elsewhere__"
    static let paces = [100, 250, 500, 750, 1000, 1500, 2000]
    static let propertyTypes = ["Single Family", "Condo", "Townhouse", "Multi-Family", "Manufactured", "Land"]

    init() {}

    init(_ d: AssetDetailsInfo?, enabled: Bool?) {
        self.enabled = enabled ?? true
        guard let d else { return }
        addressLine = d.address_line ?? ""
        city = d.city ?? ""
        state = d.state ?? ""
        zip = d.zip ?? ""
        vin = d.vin ?? ""
        mileage = d.mileage.map { String(Int($0)) } ?? ""
        milesPerMonth = d.miles_per_month.map { Int($0) } ?? 1000
        keptAt = d.garage_account_id ?? ((d.zip ?? "").isEmpty ? "" : Self.elsewhere)
    }

    /// What's wrong, field by field (empty fields are allowed: the value just waits for them).
    func problems(kind: String) -> [String: String] {
        var out: [String: String] = [:]
        let z = zip.trimmingCharacters(in: .whitespaces)
        if !z.isEmpty, z.range(of: #"^\d{5}(-\d{4})?$"#, options: .regularExpression) == nil { out["zip"] = "Five digits" }
        let s = state.trimmingCharacters(in: .whitespaces)
        if !s.isEmpty, s.range(of: #"^[A-Za-z]{2}$"#, options: .regularExpression) == nil { out["state"] = "Two letters" }
        let v = vin.trimmingCharacters(in: .whitespaces).uppercased()
        if kind == "vehicle", !v.isEmpty, v.range(of: #"^[A-HJ-NPR-Z0-9]{17}$"#, options: .regularExpression) == nil {
            out["vin"] = "17 letters and digits (no I, O or Q)"
        }
        return out
    }

    /// The body for PUT /accounts/{id}/asset (or the `asset` of a new offline account).
    func body(kind: String) -> JSONBody {
        var b = JSONBody(["valuation_enabled": .bool(enabled)])
        let home = keptAt.isEmpty || keptAt == Self.elsewhere ? nil : keptAt
        let address = kind == "home" || home == nil
        if address {
            b["address_line"] = .text(addressLine)
            b["city"] = .text(city)
            b["state"] = .text(state.uppercased())
            b["zip"] = .text(zip)
        }
        if kind == "home" {
            b["property_type"] = .text(propertyType)
            b["bedrooms"] = .num(Parse.number(bedrooms))
            b["bathrooms"] = .num(Parse.number(bathrooms))
            b["square_feet"] = .num(Parse.number(squareFeet))
        } else {
            b["vin"] = .text(vin.uppercased())
            b["mileage"] = .num(Parse.number(mileage))
            b["miles_per_month"] = .number(Double(milesPerMonth))
            b["garage_account_id"] = .text(home)
        }
        return b
    }
}

/// The fields themselves, shared by the market-value sheet and "Add offline account".
struct AssetFields: View {
    /// home | vehicle
    let kind: String
    @Binding var draft: AssetDraft
    /// The household's offline homes, for where a car is kept.
    let homes: [Account]

    var body: some View {
        let bad = draft.problems(kind: kind)
        VStack(alignment: .leading, spacing: 14) {
            if kind == "home" {
                address(bad)
                MenuField(label: "kind of home", current: draft.propertyType.isEmpty ? "let the market data decide" : draft.propertyType.lowercased()) {
                    Button("let the market data decide") { draft.propertyType = "" }
                    ForEach(AssetDraft.propertyTypes, id: \.self) { t in Button(t.lowercased()) { draft.propertyType = t } }
                }
                HStack(spacing: 10) {
                    Field(label: "bedrooms", text: $draft.bedrooms, mono: true, keyboard: .numberPad)
                    Field(label: "bathrooms", text: $draft.bathrooms, mono: true, keyboard: .decimalPad)
                    Field(label: "square feet", text: $draft.squareFeet, mono: true, keyboard: .numberPad)
                }
                Fine("Bedrooms, bathrooms and size are optional: the market data looks them up from the address.")
            } else {
                Field(label: "VIN", text: $draft.vin, placeholder: "17 letters and digits", mono: true, keyboard: .asciiCapable,
                      help: "On the driver's side of the dashboard, the door jamb, or the registration.", error: bad["vin"], uppercase: true)
                Field(label: "mileage now", text: $draft.mileage, placeholder: "30000", mono: true, keyboard: .numberPad)
                MenuField(label: "miles a month", current: Fmt.number(Double(draft.milesPerMonth)),
                          help: "Between your updates, the mileage counts up at this pace (a city car might do 100–250 a month).") {
                    ForEach(AssetDraft.paces, id: \.self) { p in Button(Fmt.number(Double(p))) { draft.milesPerMonth = p } }
                }
                MenuField(label: "kept at", current: keptAtLabel, help: "Car prices are local: the ZIP where it's kept prices it.") {
                    ForEach(homes) { h in Button(h.name + (h.asset_place.map { " · \($0)" } ?? "")) { draft.keptAt = h.id } }
                    Button("Another address…") { draft.keptAt = AssetDraft.elsewhere }
                }
                if draft.keptAt == AssetDraft.elsewhere { address(bad) }
            }
            ToggleRow(title: "Value it from market data once a month", on: $draft.enabled)
        }
    }

    private var keptAtLabel: String {
        if draft.keptAt == AssetDraft.elsewhere { return "another address" }
        if let h = homes.first(where: { $0.id == draft.keptAt }) { return h.name }
        return "choose where it's kept"
    }

    @ViewBuilder private func address(_ bad: [String: String]) -> some View {
        Field(label: kind == "home" ? "street address" : "garage street address", text: $draft.addressLine, placeholder: "12 Elm St", capitalization: .words)
        HStack(alignment: .top, spacing: 10) {
            Field(label: "city", text: $draft.city, capitalization: .words)
            Field(label: "state", text: $draft.state, placeholder: "NJ", mono: true, keyboard: .asciiCapable, error: bad["state"], uppercase: true)
                .frame(width: 70)
            Field(label: "ZIP", text: $draft.zip, placeholder: "07042", mono: true, keyboard: .numberPad, error: bad["zip"])
                .frame(width: 96)
        }
    }
}

/// An offline home's or car's market-value details (PUT /accounts/{id}/asset).
struct AssetSheet: View {
    let account: Account
    let info: AssetInfo?
    let onSaved: (AssetInfo) -> Void
    @State private var draft: AssetDraft
    @State private var homes: [Account] = []

    init(account: Account, info: AssetInfo?, onSaved: @escaping (AssetInfo) -> Void) {
        self.account = account
        self.info = info
        self.onSaved = onSaved
        _draft = State(initialValue: AssetDraft(info?.details, enabled: info?.valuation_enabled))
    }

    private var kind: String { account.manual_category == "vehicle" ? "vehicle" : "home" }

    var body: some View {
        FormSheet(title: "Market value", canSave: draft.problems(kind: kind).isEmpty, save: save) {
            Fine(kind == "home"
                 ? "With its address, it's valued from market data once a month."
                 : "With its VIN, mileage and where it's kept, it's valued from market data once a month (a dealer-retail estimate).")
            Panel(kind == "home" ? "the home" : "the car") {
                AssetFields(kind: kind, draft: $draft, homes: homes)
            }
        }
        .task {
            homes = ((try? await APIClient.shared.accounts()) ?? []).filter { $0.isManual && $0.manual_category == "real_estate" && $0.id != account.id }
        }
    }

    private func save() async throws {
        onSaved(try await APIClient.shared.putAsset(id: account.id, draft.body(kind: kind)))
    }
}

/// A new offline account: a home, a car, cash kept outside a bank, another
/// asset or another debt, with today's value (POST /accounts/manual), as the
/// dashboard's "Add offline asset".
struct AddOfflineSheet: View {
    let onAdded: (Account) -> Void
    @State private var name = ""
    @State private var category = "real_estate"
    @State private var value = ""
    @State private var draft = AssetDraft()
    @State private var homes: [Account] = []

    private static let categories = [
        ("real_estate", "real estate"), ("vehicle", "vehicle"), ("cash", "cash (not in a bank)"),
        ("other_asset", "other asset"), ("other_liability", "other liability"),
    ]

    private var kind: String? { category == "real_estate" ? "home" : category == "vehicle" ? "vehicle" : nil }
    private var parsed: Double? { Parse.money(value) }
    private var canSave: Bool {
        !name.trimmingCharacters(in: .whitespaces).isEmpty && parsed != nil && (kind.map { draft.problems(kind: $0).isEmpty } ?? true)
    }

    var body: some View {
        FormSheet(title: "Add offline account", saveLabel: "Add", canSave: canSave, save: save) {
            Panel("what it is") {
                VStack(alignment: .leading, spacing: 14) {
                    Field(label: "name", text: $name, placeholder: kind == "vehicle" ? "2020 Subaru Outback" : "123 Main St", capitalization: .words)
                    ChoiceField(label: "type", options: Self.categories, value: $category)
                    Field(label: category == "other_liability" ? "owed today" : "value today", text: $value, placeholder: "300000", mono: true,
                          keyboard: .decimalPad, help: "What you'd put on a balance sheet today. A debt as a positive amount owed.",
                          error: value.isEmpty || parsed != nil ? nil : "a number")
                }
            }
            if let kind {
                Panel(kind == "home" ? "market value" : "market value") {
                    VStack(alignment: .leading, spacing: 14) {
                        Fine((kind == "home"
                              ? "With its address, it's valued from market data once a month."
                              : "With its VIN, mileage and where it's kept, it's valued from market data once a month.") + " You can skip this and add it later.")
                        AssetFields(kind: kind, draft: $draft, homes: homes)
                    }
                }
            }
        }
        .task { homes = ((try? await APIClient.shared.accounts()) ?? []).filter { $0.isManual && $0.manual_category == "real_estate" } }
    }

    private func save() async throws {
        guard let v = parsed else { return }
        var b = JSONBody(["name": .string(name.trimmingCharacters(in: .whitespaces)), "manual_category": .string(category), "value": .money(v)])
        if let kind { b["asset"] = .object(draft.body(kind: kind).fields) }
        onAdded(try await APIClient.shared.createManual(b))
    }
}
