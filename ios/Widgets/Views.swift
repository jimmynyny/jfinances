import JFinancesKit
import SwiftUI
import WidgetKit

// MARK: - shared pieces

/// A figure in a widget: dots when the widget hides amounts, and always
/// privacy-sensitive, so a locked phone shows it redacted.
struct Figure: View {
    let text: String
    let show: Bool
    var font: Font
    var color: Color = JF.ink

    var body: some View {
        Text(show ? text : "••••")
            .font(font)
            .foregroundStyle(color)
            .lineLimit(1)
            .minimumScaleFactor(0.5)
            .privacySensitive()
    }
}

struct WidgetCaption: View {
    let text: String
    var body: some View {
        HStack(spacing: 5) {
            Rectangle().fill(JF.accent).frame(width: 5, height: 5).widgetAccentable()
            Text(text).font(JFFont.mono(10, .medium)).foregroundStyle(JF.ink2).lineLimit(1)
        }
    }
}

struct WidgetFoot: View {
    let fetchedAt: Date?
    let stale: Bool
    var body: some View {
        if let fetchedAt {
            HStack(spacing: 3) {
                if stale { Image(systemName: "wifi.slash").font(.system(size: 8)) }
                Text(fetchedAt, style: .time)
            }
            .font(JFFont.mono(9))
            .foregroundStyle(JF.ink3)
        }
    }
}

/// Not signed in, or nothing cached yet.
struct WidgetEmpty: View {
    let linked: Bool
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            WidgetCaption(text: "jfinances")
            Spacer(minLength: 0)
            Text(linked ? "Waiting for the first update." : "Open jfinances and sign in.")
                .font(JFFont.sans(13, .medium))
                .foregroundStyle(JF.ink2)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .leading)
    }
}

extension View {
    func panelBackground() -> some View {
        containerBackground(for: .widget) { JF.panel }
    }
}

private func deltaText(_ c: Change?) -> (String, Color)? {
    guard let c else { return nil }
    let arrow = c.amount > 0 ? "▲" : c.amount < 0 ? "▼" : "—"
    let color = c.amount > 0 ? JF.pos : c.amount < 0 ? JF.neg : JF.ink3
    let pct = c.pct.map { " " + Fmt.pct(abs($0), ratio: false) } ?? ""
    return ("\(arrow) \(Fmt.compact(abs(c.amount)))\(pct)", color)
}

// MARK: - net worth

struct NetWorthView: View {
    @Environment(\.widgetFamily) private var family
    let entry: GlanceEntry<NetWorthIntent>

    var body: some View {
        let show = entry.configuration.showAmounts
        Group {
            if let g = entry.glance {
                let nw = g.net_worth
                let delta = deltaText(nw.change_1m)
                switch family {
                case .accessoryInline:
                    Text(show ? "Net worth \(Fmt.compact(nw.net))" : "Net worth").privacySensitive()
                case .accessoryCircular:
                    ZStack {
                        AccessoryWidgetBackground()
                        VStack(spacing: 0) {
                            Text("NET").font(JFFont.mono(9, .semibold))
                            Figure(text: Fmt.compact(nw.net).replacingOccurrences(of: "$", with: ""), show: show, font: JFFont.mono(13, .semibold))
                        }
                    }
                case .accessoryRectangular:
                    VStack(alignment: .leading, spacing: 1) {
                        Text("Net worth").font(JFFont.mono(11, .semibold)).widgetAccentable()
                        Figure(text: Fmt.money(nw.net, cents: false), show: show, font: JFFont.pixel(22))
                        if let delta, show { Text(delta.0 + " · 30d").font(JFFont.mono(10)).privacySensitive() }
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                case .systemMedium:
                    HStack(alignment: .top, spacing: 14) {
                        VStack(alignment: .leading, spacing: 6) {
                            WidgetCaption(text: "net worth")
                            Figure(text: Fmt.money(nw.net, cents: false), show: show, font: JFFont.pixel(30)).widgetAccentable()
                            if let delta { Figure(text: delta.0 + " · 30d", show: show, font: JFFont.mono(11, .medium), color: delta.1) }
                            Spacer(minLength: 0)
                            HStack(spacing: 10) {
                                VStack(alignment: .leading, spacing: 1) {
                                    Text("owned").font(JFFont.mono(9)).foregroundStyle(JF.ink3)
                                    Figure(text: Fmt.compact(nw.assets), show: show, font: JFFont.mono(12, .medium))
                                }
                                VStack(alignment: .leading, spacing: 1) {
                                    Text("owed").font(JFFont.mono(9)).foregroundStyle(JF.ink3)
                                    Figure(text: Fmt.compact(nw.liabilities), show: show, font: JFFont.mono(12, .medium))
                                }
                            }
                        }
                        VStack(alignment: .trailing, spacing: 4) {
                            PixelSparkline(nw.points.map(\.net), cell: 3, gap: 1).frame(maxHeight: .infinity)
                            WidgetFoot(fetchedAt: entry.fetchedAt, stale: entry.status == .stale)
                        }
                    }
                default:
                    VStack(alignment: .leading, spacing: 5) {
                        WidgetCaption(text: "net worth")
                        Figure(text: Fmt.money(nw.net, cents: false), show: show, font: JFFont.pixel(34)).widgetAccentable()
                        if let delta { Figure(text: delta.0, show: show, font: JFFont.mono(11, .medium), color: delta.1) }
                        Spacer(minLength: 2)
                        PixelSparkline(nw.points.map(\.net), cell: 3, gap: 1).frame(height: 30)
                        WidgetFoot(fetchedAt: entry.fetchedAt, stale: entry.status == .stale)
                    }
                }
            } else {
                WidgetEmpty(linked: entry.status != .notLinked)
            }
        }
        .panelBackground()
    }
}

// MARK: - this month

struct MonthView: View {
    @Environment(\.widgetFamily) private var family
    let entry: GlanceEntry<MonthIntent>

    private func monthName(_ m: GlanceMonth) -> String {
        (Fmt.day(m.from) ?? Date()).formatted(.dateTime.month(.wide)).lowercased()
    }

    var body: some View {
        let show = entry.configuration.showAmounts
        Group {
            if let g = entry.glance {
                let m = g.month
                let total = m.categories.reduce(0) { $0 + $1.amount }
                switch family {
                case .accessoryRectangular:
                    VStack(alignment: .leading, spacing: 1) {
                        Text(monthName(m).capitalized).font(JFFont.mono(11, .semibold)).widgetAccentable()
                        Figure(text: "out " + Fmt.compact(m.spending), show: show, font: JFFont.mono(13, .medium))
                        Figure(text: "in " + Fmt.compact(m.income), show: show, font: JFFont.mono(13, .medium))
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                case .systemSmall:
                    VStack(alignment: .leading, spacing: 5) {
                        WidgetCaption(text: monthName(m))
                        Text("money out").font(JFFont.mono(9)).foregroundStyle(JF.ink3)
                        Figure(text: Fmt.money(m.spending, cents: false), show: show, font: JFFont.pixel(30)).widgetAccentable()
                        if m.income > 0 {
                            PixelMeter(ratio: min(1, m.spending / m.income), cells: 16, tone: m.spending > m.income ? .neg : .accent, height: 6)
                        }
                        Spacer(minLength: 0)
                        HStack {
                            Text("in").font(JFFont.mono(10)).foregroundStyle(JF.ink3)
                            Figure(text: Fmt.compact(m.income), show: show, font: JFFont.mono(11, .medium))
                            Spacer()
                            Figure(text: Fmt.compact(m.net), show: show, font: JFFont.mono(11, .medium), color: m.net >= 0 ? JF.pos : JF.neg)
                        }
                    }
                default:
                    VStack(alignment: .leading, spacing: 8) {
                        HStack {
                            WidgetCaption(text: monthName(m))
                            Spacer()
                            WidgetFoot(fetchedAt: entry.fetchedAt, stale: entry.status == .stale)
                        }
                        HStack(alignment: .top, spacing: 12) {
                            stat("money in", m.income, show)
                            stat("money out", m.spending, show)
                            stat("net", m.net, show, color: m.net >= 0 ? JF.pos : JF.neg)
                        }
                        if family == .systemLarge, total > 0 {
                            let slices = waffleSlices(m.categories.map { (key: $0.key, label: Category.label($0.key), value: $0.amount) })
                            HStack(alignment: .top, spacing: 14) {
                                WaffleGrid(slices).frame(width: 128, height: 128)
                                VStack(alignment: .leading, spacing: 6) {
                                    ForEach(slices) { s in
                                        HStack(spacing: 6) {
                                            Rectangle().fill(s.color).frame(width: 7, height: 7)
                                            Text(s.label).font(JFFont.sans(12)).foregroundStyle(JF.ink).lineLimit(1)
                                            Spacer(minLength: 4)
                                            Figure(text: Fmt.compact(s.value), show: show, font: JFFont.mono(11))
                                        }
                                    }
                                }
                            }
                            Spacer(minLength: 0)
                        } else if total > 0 {
                            VStack(spacing: 5) {
                                ForEach(Array(m.categories.prefix(3).enumerated()), id: \.element.id) { i, c in
                                    HStack(spacing: 8) {
                                        Text(Category.label(c.key)).font(JFFont.sans(11)).foregroundStyle(JF.ink).lineLimit(1)
                                            .frame(width: 104, alignment: .leading)
                                        PixelMeter(ratio: c.amount / total, cells: 14, tone: .series(i), height: 5)
                                        Figure(text: Fmt.compact(c.amount), show: show, font: JFFont.mono(10))
                                            .frame(width: 44, alignment: .trailing)
                                    }
                                }
                            }
                        }
                    }
                }
            } else {
                WidgetEmpty(linked: entry.status != .notLinked)
            }
        }
        .panelBackground()
    }

    private func stat(_ label: String, _ value: Double, _ show: Bool, color: Color = JF.ink) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label).font(JFFont.mono(9)).foregroundStyle(JF.ink3)
            Figure(text: Fmt.money(value, cents: false), show: show, font: JFFont.pixel(20), color: color)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

// MARK: - coming up

struct UpcomingView: View {
    @Environment(\.widgetFamily) private var family
    let entry: GlanceEntry<UpcomingIntent>

    private func when(_ item: UpcomingCharge) -> String {
        switch Fmt.daysUntil(item.date) {
        case 0: return item.overdue ? "due" : "today"
        case 1: return "tmrw"
        default: return Fmt.date(item.date)
        }
    }

    var body: some View {
        let show = entry.configuration.showAmounts
        Group {
            if let g = entry.glance {
                let up = g.upcoming
                switch family {
                case .accessoryRectangular:
                    VStack(alignment: .leading, spacing: 1) {
                        Text("Coming up").font(JFFont.mono(11, .semibold)).widgetAccentable()
                        if let next = up.items.first {
                            Text("\(next.label) · \(when(next))").font(JFFont.sans(13, .medium)).lineLimit(1)
                            Figure(text: Fmt.money(next.amount), show: show, font: JFFont.mono(12))
                        } else {
                            Text("Nothing due").font(JFFont.sans(13))
                        }
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                case .systemSmall:
                    VStack(alignment: .leading, spacing: 4) {
                        WidgetCaption(text: "coming up")
                        if let next = up.items.first {
                            Text(when(next)).font(JFFont.mono(10, .medium)).foregroundStyle(next.overdue ? JF.neg : JF.accentText)
                            Text(next.label).font(JFFont.sans(15, .semibold)).foregroundStyle(JF.ink).lineLimit(2)
                            Figure(text: Fmt.money(next.amount), show: show, font: JFFont.mono(20, .semibold)).widgetAccentable()
                        } else {
                            Text("Nothing due in two weeks.").font(JFFont.sans(13)).foregroundStyle(JF.ink2)
                        }
                        Spacer(minLength: 0)
                        HStack(spacing: 4) {
                            Text("14 days").font(JFFont.mono(9)).foregroundStyle(JF.ink3)
                            Figure(text: Fmt.compact(up.total), show: show, font: JFFont.mono(10, .medium))
                        }
                    }
                default:
                    let n = family == .systemLarge ? 9 : 4
                    VStack(alignment: .leading, spacing: 6) {
                        HStack {
                            WidgetCaption(text: "coming up · 14 days")
                            Spacer()
                            Figure(text: Fmt.compact(up.total), show: show, font: JFFont.mono(11, .semibold))
                        }
                        if up.items.isEmpty {
                            Text("Nothing expected.").font(JFFont.sans(13)).foregroundStyle(JF.ink2)
                        }
                        ForEach(Array(up.items.prefix(n).enumerated()), id: \.element.id) { i, item in
                            HStack(spacing: 8) {
                                Text(when(item)).font(JFFont.mono(10, .medium)).foregroundStyle(item.overdue ? JF.neg : JF.ink2)
                                    .frame(width: 44, alignment: .leading)
                                Text(item.label).font(JFFont.sans(13, .medium)).foregroundStyle(JF.ink).lineLimit(1)
                                if item.is_business == true { BusinessMark() }
                                Spacer(minLength: 4)
                                Figure(text: Fmt.money(item.amount), show: show, font: JFFont.mono(12))
                            }
                            if i < min(n, up.items.count) - 1 { Rule() }
                        }
                        Spacer(minLength: 0)
                        if up.items.count > n {
                            Text("and \(up.items.count - n) more").font(JFFont.mono(9)).foregroundStyle(JF.ink3)
                        }
                    }
                }
            } else {
                WidgetEmpty(linked: entry.status != .notLinked)
            }
        }
        .panelBackground()
    }
}

// MARK: - one account

struct AccountView: View {
    @Environment(\.widgetFamily) private var family
    let entry: GlanceEntry<AccountIntent>

    var body: some View {
        let show = entry.configuration.showAmounts
        let account = entry.glance.flatMap { g in
            entry.configuration.account.flatMap { sel in g.accounts.first { $0.id == sel.id } } ?? g.accounts.first
        }
        Group {
            if let a = account {
                switch family {
                case .accessoryInline:
                    Text(show ? "\(a.name) \(Fmt.compact(a.balance))" : a.name).privacySensitive()
                case .accessoryCircular:
                    ZStack {
                        AccessoryWidgetBackground()
                        VStack(spacing: 0) {
                            Text(String(a.name.prefix(4)).uppercased()).font(JFFont.mono(8, .semibold)).lineLimit(1)
                            Figure(text: Fmt.compact(a.balance).replacingOccurrences(of: "$", with: ""), show: show, font: JFFont.mono(12, .semibold))
                        }
                        .padding(4)
                    }
                case .accessoryRectangular:
                    VStack(alignment: .leading, spacing: 1) {
                        Text(a.name).font(JFFont.mono(11, .semibold)).lineLimit(1).widgetAccentable()
                        Figure(text: Fmt.money(a.balance, cents: false), show: show, font: JFFont.pixel(22))
                        Text(a.subtitle).font(JFFont.mono(10)).lineLimit(1)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                default:
                    VStack(alignment: .leading, spacing: 4) {
                        WidgetCaption(text: a.is_liability ? "owed" : "balance")
                        HStack(spacing: 5) {
                            Text(a.name).font(JFFont.sans(14, .semibold)).foregroundStyle(JF.ink).lineLimit(1)
                            if a.is_business == true { BusinessMark() }
                        }
                        Text(a.subtitle).font(JFFont.mono(10)).foregroundStyle(JF.ink3).lineLimit(1)
                        Spacer(minLength: 0)
                        Figure(text: Fmt.money(a.balance, cents: false, currency: a.currency), show: show, font: JFFont.pixel(26)).widgetAccentable()
                        if a.trendValues.count >= 2 { PixelSparkline(a.trendValues, cell: 3, gap: 1).frame(height: 22) }
                    }
                }
            } else {
                WidgetEmpty(linked: entry.status != .notLinked)
            }
        }
        .panelBackground()
    }
}
