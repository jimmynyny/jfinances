import Charts
import JFinancesKit
import SwiftUI

// Swift Charts, dressed in the design system: mono axis labels in ink-3,
// gridlines one step off the surface, the accent for the hero series, and
// every figure blurred with the switch.

struct DatedValue: Identifiable, Hashable {
    let date: Date
    let value: Double
    var id: Date { date }
}

extension Array where Element == DatedValue {
    var domain: ClosedRange<Double> {
        let lo = map(\.value).min() ?? 0
        let hi = map(\.value).max() ?? 0
        let pad = Swift.max((hi - lo) * 0.12, Swift.max(abs(hi) * 0.002, 1))
        return (lo - pad)...(hi + pad)
    }
}

private struct AxisText: View {
    let text: String
    var body: some View {
        Text(text).font(JFFont.mono(10)).foregroundStyle(JF.ink3).figure(size: 10)
    }
}

/// A line with a soft fill: net worth, a balance. Press and drag to read a day.
struct TrendChart: View {
    let points: [DatedValue]
    var color: Color = JF.accent
    var estimatedBefore: Date?
    var height: CGFloat = 180
    var format: (Double) -> String = { Fmt.compact($0) }
    @State private var selected: Date?

    private var selectedPoint: DatedValue? {
        guard let selected else { return nil }
        return points.min { abs($0.date.timeIntervalSince(selected)) < abs($1.date.timeIntervalSince(selected)) }
    }

    var body: some View {
        let domain = points.domain
        Chart {
            if let est = estimatedBefore, let first = points.first?.date, est > first {
                RectangleMark(xStart: .value("From", first), xEnd: .value("To", est))
                    .foregroundStyle(JF.panel2)
                    .annotation(position: .overlay, alignment: .topLeading) {
                        Text("estimated").font(JFFont.mono(9)).foregroundStyle(JF.ink3).padding(4)
                    }
            }
            ForEach(points) { p in
                AreaMark(x: .value("Date", p.date), yStart: .value("Base", domain.lowerBound), yEnd: .value("Value", p.value))
                    .foregroundStyle(LinearGradient(colors: [color.opacity(0.22), color.opacity(0.0)], startPoint: .top, endPoint: .bottom))
                    .interpolationMethod(.monotone)
                LineMark(x: .value("Date", p.date), y: .value("Value", p.value))
                    .foregroundStyle(color)
                    .lineStyle(StrokeStyle(lineWidth: 2))
                    .interpolationMethod(.monotone)
            }
            if let s = selectedPoint {
                RuleMark(x: .value("Date", s.date))
                    .foregroundStyle(JF.ink3)
                    .lineStyle(StrokeStyle(lineWidth: 1, dash: [2, 2]))
                PointMark(x: .value("Date", s.date), y: .value("Value", s.value))
                    .foregroundStyle(color)
                    .symbolSize(36)
                    .annotation(position: .top, spacing: 6, overflowResolution: .init(x: .fit(to: .chart), y: .disabled)) {
                        Tip(title: Fmt.date(Fmt.isoDay(s.date), year: true), value: Fmt.money(s.value, cents: false))
                    }
            }
        }
        .chartYScale(domain: domain)
        .chartXSelection(value: $selected)
        .chartYAxis {
            AxisMarks(position: .trailing, values: .automatic(desiredCount: 4)) { v in
                AxisGridLine().foregroundStyle(JF.grid)
                AxisValueLabel { if let d = v.as(Double.self) { AxisText(text: format(d)) } }
            }
        }
        .chartXAxis {
            AxisMarks(values: .automatic(desiredCount: 4)) { v in
                AxisValueLabel {
                    if let d = v.as(Date.self) { AxisText(text: d.formatted(.dateTime.month(.abbreviated).day())) }
                }
            }
        }
        .frame(height: height)
        .accessibilityLabel("Trend chart")
    }
}

/// The selection tooltip: date in mono, figure blurred with the switch, and
/// what a second tap opens.
struct Tip: View {
    let title: String
    let value: String
    var hint: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(title).font(JFFont.mono(10)).foregroundStyle(JF.ink3)
            Text(value).font(JFFont.mono(12, .semibold)).foregroundStyle(JF.ink).figure(size: 12)
            if let hint { Text(hint).font(JFFont.mono(10)).foregroundStyle(JF.accentText) }
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 5)
        .background(JF.panel)
        .overlay(Rectangle().strokeBorder(JF.lineStrong, lineWidth: 1))
    }
}

/// Money in and out per period, side by side. The legend hides either side; a
/// tap shows a period's numbers and a second tap on the same bar opens its
/// transactions (`onOpen` with "income" or "spending").
struct FlowBarsChart: View {
    let periods: [CashflowPeriod]
    var height: CGFloat = 190
    var onOpen: ((CashflowPeriod, String) -> Void)?
    @State private var picked: Pick?
    @State private var hidden: Set<String> = []

    private struct Pick: Equatable { let period: String; let kind: String }

    private func short(_ p: CashflowPeriod) -> String { p.label.components(separatedBy: " ").first ?? p.label }
    private var kinds: [String] { ["In", "Out"].filter { !hidden.contains($0) } }

    private func faded(_ p: CashflowPeriod, _ kind: String) -> Double {
        guard let picked else { return 1 }
        return picked.period == p.period && picked.kind == kind ? 1 : 0.35
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            LegendToggles(items: [.init(key: "In", label: "money in", color: JF.divPos),
                                  .init(key: "Out", label: "money out", color: JF.divNeg)], hidden: $hidden)
            Chart {
                ForEach(periods) { p in
                    if !hidden.contains("In") {
                        BarMark(x: .value("Period", p.period), y: .value("Amount", p.income), width: .ratio(0.85))
                            .foregroundStyle(by: .value("Kind", "In"))
                            .position(by: .value("Kind", "In"))
                            .opacity(faded(p, "In"))
                    }
                    if !hidden.contains("Out") {
                        BarMark(x: .value("Period", p.period), y: .value("Amount", p.spending), width: .ratio(0.85))
                            .foregroundStyle(by: .value("Kind", "Out"))
                            .position(by: .value("Kind", "Out"))
                            .opacity(faded(p, "Out"))
                    }
                }
                if let pk = picked, let p = periods.first(where: { $0.period == pk.period }) {
                    RuleMark(x: .value("Period", pk.period))
                        .foregroundStyle(JF.ink3.opacity(0.0))
                        .annotation(position: .top, spacing: 0, overflowResolution: .init(x: .fit(to: .chart), y: .disabled)) {
                            Tip(title: p.label, value: "in \(Fmt.compact(p.income)) · out \(Fmt.compact(p.spending))",
                                hint: onOpen == nil ? nil : "tap again: money \(pk.kind == "In" ? "in" : "out")")
                        }
                }
            }
            .chartForegroundStyleScale(["In": JF.divPos, "Out": JF.divNeg])
            .chartLegend(.hidden)
            .chartOverlay { proxy in
                GeometryReader { geo in
                    Rectangle().fill(.clear).contentShape(Rectangle())
                        .onTapGesture { loc in tap(loc, proxy, geo) }
                }
            }
            .chartYAxis {
                AxisMarks(position: .trailing, values: .automatic(desiredCount: 4)) { v in
                    AxisGridLine().foregroundStyle(JF.grid)
                    AxisValueLabel { if let d = v.as(Double.self) { AxisText(text: Fmt.compact(d)) } }
                }
            }
            .chartXAxis {
                AxisMarks { v in
                    AxisValueLabel {
                        if let s = v.as(String.self), let p = periods.first(where: { $0.period == s }) { AxisText(text: short(p)) }
                    }
                }
            }
            .frame(height: height)
        }
    }

    private func tap(_ loc: CGPoint, _ proxy: ChartProxy, _ geo: GeometryProxy) {
        guard let plot = proxy.plotFrame else { return }
        let x = loc.x - geo[plot].origin.x
        guard let period: String = proxy.value(atX: x), let p = periods.first(where: { $0.period == period }),
              let first = kinds.first else { picked = nil; return }
        // Side by side: the left half of a period's slot is money in, the right half money out.
        var kind = first
        if kinds.count == 2, let center = proxy.position(forX: period) { kind = x < center ? "In" : "Out" }
        let pick = Pick(period: period, kind: kind)
        if picked == pick, let onOpen {
            picked = nil
            onOpen(p, kind == "In" ? "income" : "spending")
        } else {
            picked = pick
        }
    }
}

/// A chart's legend that toggles its series (the web's legends): a hidden series
/// leaves the chart and its scale, colours stay put, and the last one can't be hidden.
struct LegendToggles: View {
    struct Item: Identifiable {
        let key: String
        let label: String
        let color: Color
        var id: String { key }
    }

    let items: [Item]
    @Binding var hidden: Set<String>

    var body: some View {
        FlowLayout(spacing: 6) {
            ForEach(items) { item in
                ToggleChip(label: item.label, color: item.color, on: !hidden.contains(item.key)) {
                    if hidden.contains(item.key) {
                        hidden.remove(item.key)
                    } else if items.filter({ !hidden.contains($0.key) }).count > 1 {
                        hidden.insert(item.key)
                    }
                }
            }
        }
    }
}

/// Spending per period, stacked by category, in fixed series order. Hidden
/// series leave the chart (colours stay put); a tap shows a period's category
/// and a second tap on it opens its transactions (`onOpen` with the series key
/// and the period).
struct StackedSpendingChart: View {
    let spending: Spending
    var hidden: Set<String> = []
    var height: CGFloat = 210
    var labelFor: (String) -> String = { Category.label($0) }
    var onOpen: ((String, PeriodLabel) -> Void)?
    @State private var picked: Pick?

    private struct Pick: Equatable { let period: String; let key: String }

    private struct Cell: Identifiable {
        let period: String
        let key: String
        let label: String
        let value: Double
        var id: String { period + key }
    }

    private var cells: [Cell] {
        spending.series.filter { !hidden.contains($0.key) }.flatMap { s in
            s.numbers.enumerated().compactMap { i, v in
                i < spending.periods.count ? Cell(period: spending.periods[i].period, key: s.key, label: labelFor(s.key), value: v) : nil
            }
        }
    }

    var body: some View {
        let labels = spending.series.map { labelFor($0.key) }
        let colors = spending.series.indices.map { i in spending.series[i].key == "OTHER" ? JF.other : JF.seriesColor(i) }
        Chart {
            ForEach(cells) { c in
                BarMark(x: .value("Period", c.period), y: .value("Amount", c.value), width: .ratio(0.7))
                    .foregroundStyle(by: .value("Category", c.label))
                    .opacity(picked == nil || picked == Pick(period: c.period, key: c.key) ? 1 : 0.35)
            }
            if let pk = picked, let p = spending.periods.first(where: { $0.period == pk.period }),
               let c = cells.first(where: { $0.period == pk.period && $0.key == pk.key }) {
                RuleMark(x: .value("Period", pk.period))
                    .foregroundStyle(JF.ink3.opacity(0.0))
                    .annotation(position: .top, spacing: 0, overflowResolution: .init(x: .fit(to: .chart), y: .disabled)) {
                        Tip(title: "\(p.label) · \(c.label)", value: Fmt.money(c.value, cents: false),
                            hint: onOpen == nil ? nil : "tap again: see these")
                    }
            }
        }
        .chartForegroundStyleScale(domain: labels, range: colors)
        .chartLegend(.hidden)
        .chartOverlay { proxy in
            GeometryReader { geo in
                Rectangle().fill(.clear).contentShape(Rectangle())
                    .onTapGesture { loc in tap(loc, proxy, geo) }
            }
        }
        .chartYAxis {
            AxisMarks(position: .trailing, values: .automatic(desiredCount: 4)) { v in
                AxisGridLine().foregroundStyle(JF.grid)
                AxisValueLabel { if let d = v.as(Double.self) { AxisText(text: Fmt.compact(d)) } }
            }
        }
        .chartXAxis {
            AxisMarks { v in
                AxisValueLabel {
                    if let s = v.as(String.self), let p = spending.periods.first(where: { $0.period == s }) {
                        AxisText(text: p.label.components(separatedBy: " ").first ?? p.label)
                    }
                }
            }
        }
        .frame(height: height)
    }

    /// Which stacked segment the tap landed in: the series stack bottom-up in order.
    private func tap(_ loc: CGPoint, _ proxy: ChartProxy, _ geo: GeometryProxy) {
        guard let plot = proxy.plotFrame else { return }
        let origin = geo[plot].origin
        guard let period: String = proxy.value(atX: loc.x - origin.x),
              let amount: Double = proxy.value(atY: loc.y - origin.y),
              let p = spending.periods.first(where: { $0.period == period }) else { picked = nil; return }
        var top = 0.0
        var key: String?
        for c in cells where c.period == period && c.value > 0 {
            top += c.value
            if amount <= top { key = c.key; break }
        }
        // Above the bar: its top segment, so a thin one is still reachable.
        if key == nil { key = cells.last(where: { $0.period == period && $0.value > 0 })?.key }
        guard let key else { picked = nil; return }
        let pick = Pick(period: period, key: key)
        if picked == pick, let onOpen {
            picked = nil
            onOpen(key, p)
        } else {
            picked = pick
        }
    }
}

/// Several cumulative-return lines (portfolio and benchmarks), in percent.
struct ReturnsChart: View {
    struct Line: Identifiable {
        let key: String
        let label: String
        let color: Color
        let points: [DatedValue]
        let emphasis: Bool
        var id: String { key }
    }

    let lines: [Line]
    var height: CGFloat = 220
    @State private var selected: Date?

    var body: some View {
        Chart {
            RuleMark(y: .value("Zero", 0)).foregroundStyle(JF.line)
            ForEach(lines) { line in
                ForEach(line.points) { p in
                    LineMark(x: .value("Date", p.date), y: .value("Return", p.value * 100), series: .value("Series", line.label))
                        .foregroundStyle(line.color)
                        .lineStyle(StrokeStyle(lineWidth: line.emphasis ? 2.5 : 1.5))
                        .interpolationMethod(.monotone)
                }
            }
            if let selected {
                RuleMark(x: .value("Date", selected))
                    .foregroundStyle(JF.ink3)
                    .lineStyle(StrokeStyle(lineWidth: 1, dash: [2, 2]))
                    .annotation(position: .top, spacing: 4, overflowResolution: .init(x: .fit(to: .chart), y: .disabled)) {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(Fmt.date(Fmt.isoDay(selected), year: true)).font(JFFont.mono(10)).foregroundStyle(JF.ink3)
                            ForEach(lines) { line in
                                if let p = line.points.min(by: { abs($0.date.timeIntervalSince(selected)) < abs($1.date.timeIntervalSince(selected)) }) {
                                    HStack(spacing: 5) {
                                        Rectangle().fill(line.color).frame(width: 6, height: 6)
                                        Text(line.label).font(JFFont.mono(10)).foregroundStyle(JF.ink2)
                                        Text(Fmt.pct(p.value, signed: true)).font(JFFont.mono(10, .semibold)).foregroundStyle(JF.ink)
                                    }
                                }
                            }
                        }
                        .padding(6)
                        .background(JF.panel)
                        .overlay(Rectangle().strokeBorder(JF.lineStrong, lineWidth: 1))
                    }
            }
        }
        .chartXSelection(value: $selected)
        .chartYAxis {
            AxisMarks(position: .trailing, values: .automatic(desiredCount: 5)) { v in
                AxisGridLine().foregroundStyle(JF.grid)
                AxisValueLabel { if let d = v.as(Double.self) { AxisText(text: "\(Int(d.rounded()))%") } }
            }
        }
        .chartXAxis {
            AxisMarks(values: .automatic(desiredCount: 4)) { v in
                AxisValueLabel {
                    if let d = v.as(Date.self) { AxisText(text: d.formatted(.dateTime.month(.abbreviated).year(.twoDigits))) }
                }
            }
        }
        .frame(height: height)
    }
}

/// Assets above the line and debts below it, per month, stacked by kind. The
/// legend hides a kind (colours stay put; the last can't be hidden).
struct ClassBarsChart: View {
    let data: NetWorthByClass
    var height: CGFloat = 230
    @State private var hidden: Set<String> = []

    private struct Cell: Identifiable {
        let date: Date
        let label: String
        let value: Double
        var id: String { "\(date.timeIntervalSince1970)" + label }
    }

    var body: some View {
        let labels = data.groups.map(\.label)
        let colors = data.groups.indices.map { JF.seriesColor($0) }
        let cells: [Cell] = data.points.flatMap { p in
            data.groups.filter { !hidden.contains($0.key) }.compactMap { g in
                Fmt.day(p["date"]?.string).map { Cell(date: $0, label: g.label, value: (g.liability ? -1 : 1) * data.value(p, g.key)) }
            }
        }
        VStack(alignment: .leading, spacing: 8) {
            Chart(cells) { c in
                BarMark(x: .value("Month", c.date, unit: .month), y: .value("Amount", c.value), width: .ratio(0.75))
                    .foregroundStyle(by: .value("Kind", c.label))
            }
            .chartForegroundStyleScale(domain: labels, range: colors)
            .chartLegend(.hidden)
            .chartYAxis {
                AxisMarks(position: .trailing, values: .automatic(desiredCount: 5)) { v in
                    AxisGridLine().foregroundStyle(JF.grid)
                    AxisValueLabel { if let d = v.as(Double.self) { AxisText(text: Fmt.compact(d)) } }
                }
            }
            .chartXAxis {
                AxisMarks(values: .automatic(desiredCount: 4)) { v in
                    AxisValueLabel {
                        if let d = v.as(Date.self) { AxisText(text: d.formatted(.dateTime.month(.abbreviated).year(.twoDigits))) }
                    }
                }
            }
            .frame(height: height)
            LegendToggles(items: data.groups.enumerated().map { i, g in .init(key: g.key, label: g.label, color: JF.seriesColor(i)) },
                          hidden: $hidden)
        }
    }
}
