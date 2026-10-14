import Foundation

/// Formatting, as the web's lib/format: money with a currency sign and
/// grouping, compact money for tight places, and plain dates.
public enum Fmt {
    public static func money(_ v: Double, cents: Bool = true, currency: String = "USD") -> String {
        v.formatted(.currency(code: currency).precision(.fractionLength(cents ? 2 : 0)).locale(locale))
    }

    /// "+$1,234.00" / "−$1,234.00" (a real minus sign).
    public static func signed(_ v: Double, cents: Bool = true, currency: String = "USD") -> String {
        let body = money(abs(v), cents: cents, currency: currency)
        return v > 0 ? "+" + body : v < 0 ? "\u{2212}" + body : body
    }

    /// "$1.09M", "$54.3k", "$812" for tight places (widgets, chart axes).
    public static func compact(_ v: Double, currency: String = "USD") -> String {
        let a = abs(v)
        let sign = v < 0 ? "\u{2212}" : ""
        let sym = currency == "USD" ? "$" : currency + " "
        func trim(_ x: Double, _ digits: Int) -> String {
            var s = String(format: "%.\(digits)f", x)
            if s.contains(".") {
                while s.hasSuffix("0") { s.removeLast() }
                if s.hasSuffix(".") { s.removeLast() }
            }
            return s
        }
        if a >= 1_000_000_000 { return "\(sign)\(sym)\(trim(a / 1_000_000_000, 2))B" }
        if a >= 1_000_000 { return "\(sign)\(sym)\(trim(a / 1_000_000, a >= 10_000_000 ? 1 : 2))M" }
        if a >= 10_000 { return "\(sign)\(sym)\(trim(a / 1000, a >= 100_000 ? 0 : 1))k" }
        if a >= 1000 { return "\(sign)\(sym)\(trim(a / 1000, 2))k" }
        return "\(sign)\(sym)\(Int(a.rounded()))"
    }

    /// 0.0123 -> "1.2%"; `ratio: false` when the value is already a percent.
    public static func pct(_ v: Double?, digits: Int = 1, ratio: Bool = true, signed: Bool = false) -> String {
        guard let v else { return "—" }
        let p = ratio ? v * 100 : v
        let s = String(format: "%.\(digits)f%%", abs(p))
        if signed { return p > 0 ? "+" + s : p < 0 ? "\u{2212}" + s : s }
        return p < 0 ? "\u{2212}" + s : s
    }

    public static func number(_ v: Double, digits: Int = 0) -> String {
        v.formatted(.number.precision(.fractionLength(digits)).locale(locale))
    }

    // MARK: - dates

    private static let locale = Locale(identifier: "en_US")

    private static let dayParser: DateFormatter = {
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.dateFormat = "yyyy-MM-dd"
        f.timeZone = .current
        return f
    }()

    /// "2026-10-14" (or a timestamp starting with one) as local midnight.
    public static func day(_ iso: String?) -> Date? {
        guard let iso, iso.count >= 10 else { return nil }
        return dayParser.date(from: String(iso.prefix(10)))
    }

    public static func isoDay(_ date: Date) -> String { dayParser.string(from: date) }

    public static func timestamp(_ iso: String?) -> Date? {
        guard let iso else { return nil }
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let d = f.date(from: iso) { return d }
        f.formatOptions = [.withInternetDateTime]
        return f.date(from: iso) ?? day(iso)
    }

    /// "Oct 14", or "Oct 14, 2025" when it is not this year.
    public static func date(_ iso: String?, year: Bool? = nil) -> String {
        guard let d = day(iso) else { return "—" }
        let showYear = year ?? (Calendar.current.component(.year, from: d) != Calendar.current.component(.year, from: Date()))
        return d.formatted(.dateTime.month(.abbreviated).day().year(showYear ? .defaultDigits : .omitted).locale(locale))
    }

    /// "Today", "Yesterday", "Mon, Oct 12".
    public static func dayHeading(_ iso: String) -> String {
        guard let d = day(iso) else { return iso }
        let cal = Calendar.current
        if cal.isDateInToday(d) { return "Today" }
        if cal.isDateInYesterday(d) { return "Yesterday" }
        if cal.isDateInTomorrow(d) { return "Tomorrow" }
        let sameYear = cal.component(.year, from: d) == cal.component(.year, from: Date())
        return d.formatted(.dateTime.weekday(.abbreviated).month(.abbreviated).day()
            .year(sameYear ? .omitted : .defaultDigits).locale(locale))
    }

    /// "3 min ago", "2 h ago", "Oct 4".
    public static func relative(_ iso: String?) -> String {
        guard let d = timestamp(iso) else { return "—" }
        let s = Date().timeIntervalSince(d)
        if s < 60 { return "just now" }
        if s < 3600 { return "\(Int(s / 60)) min ago" }
        if s < 86_400 { return "\(Int(s / 3600)) h ago" }
        if s < 7 * 86_400 { return "\(Int(s / 86_400)) d ago" }
        return date(iso)
    }

    /// Days from today to `iso` (negative = past).
    public static func daysUntil(_ iso: String) -> Int? {
        guard let d = day(iso) else { return nil }
        return Calendar.current.dateComponents([.day], from: Calendar.current.startOfDay(for: Date()), to: d).day
    }

    public static func monthLabel(_ iso: String) -> String {
        guard let d = day(iso) else { return iso }
        return d.formatted(.dateTime.month(.abbreviated).locale(locale))
    }
}

/// Category keys as the dashboard says them ("FOOD_AND_DRINK" -> "food and
/// drink"; a detailed key loses its primary's prefix).
public enum Category {
    public static func label(_ key: String?, primary: String? = nil) -> String {
        guard let key, !key.isEmpty else { return "uncategorized" }
        if key == "OTHER" { return "other" }
        if key == "PAYMENT" { return "payments" }
        var k = key
        if let primary, key.hasPrefix(primary + "_") { k = String(key.dropFirst(primary.count + 1)) }
        return k.lowercased().replacingOccurrences(of: "_", with: " ")
    }

    /// An SF Symbol for a primary category, for list rows.
    public static func symbol(_ key: String?) -> String {
        switch key ?? "" {
        case "INCOME": return "arrow.down.left"
        case "TRANSFER_IN", "TRANSFER_OUT": return "arrow.left.arrow.right"
        case "PAYMENT", "LOAN_PAYMENTS": return "creditcard"
        case "BANK_FEES": return "building.columns"
        case "ENTERTAINMENT": return "play.rectangle"
        case "FOOD_AND_DRINK": return "fork.knife"
        case "GENERAL_MERCHANDISE": return "bag"
        case "HOME_IMPROVEMENT": return "hammer"
        case "MEDICAL": return "cross.case"
        case "PERSONAL_CARE": return "sparkles"
        case "GENERAL_SERVICES": return "wrench.and.screwdriver"
        case "GOVERNMENT_AND_NON_PROFIT": return "building"
        case "TRANSPORTATION": return "car"
        case "TRAVEL": return "airplane"
        case "RENT_AND_UTILITIES": return "house"
        case "LOAN_DISBURSEMENTS": return "banknote"
        default: return "circle.grid.2x2"
        }
    }
}
