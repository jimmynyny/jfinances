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

/// The selection tooltip: date in mono, figure blurred with the switch.
struct Tip: View {
    let title: String
    let value: String

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(title).font(JFFont.mono(10)).foregroundStyle(JF.ink3)
            Text(value).font(JFFont.mono(12, .semibold)).foregroundStyle(JF.ink).figure(size: 12)
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 5)
        .background(JF.panel)
        .overlay(Rectangle().strokeBorder(JF.lineStrong, lineWidth: 1))
    }
}

/// Money in and out per period, side by side.
struct FlowBarsChart: View {
    let periods: [CashflowPeriod]
    var height: CGFloat = 190
    @State private var selected: String?

    private func short(_ p: CashflowPeriod) -> String { p.label.components(separatedBy: " ").first ?? p.label }

    var body: some View {
        Chart {
            ForEach(periods) { p in
                BarMark(x: .value("Period", p.period), y: .value("Amount", p.income), width: .ratio(0.85))
                    .foregroundStyle(by: .value("Kind", "In"))
                    .position(by: .value("Kind", "In"))
                BarMark(x: .value("Period", p.period), y: .value("Amount", p.spending), width: .ratio(0.85))
                    .foregroundStyle(by: .value("Kind", "Out"))
                    .position(by: .value("Kind", "Out"))
            }
            if let s = selected, let p = periods.first(where: { $0.period == s }) {
                RuleMark(x: .value("Period", s))
                    .foregroundStyle(JF.ink3.opacity(0.0))
                    .annotation(position: .top, spacing: 0, overflowResolution: .init(x: .fit(to: .chart), y: .disabled)) {
                        Tip(title: p.label, value: "in \(Fmt.compact(p.income)) · out \(Fmt.compact(p.spending))")
                    }
            }
        }
        .chartForegroundStyleScale(["In": JF.divPos, "Out": JF.divNeg])
        .chartXSelection(value: $selected)
        .chartLegend(position: .top, alignment: .leading) {
            HStack(spacing: 12) {
                LegendSwatch(color: JF.divPos, label: "money in")
                LegendSwatch(color: JF.divNeg, label: "money out")
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

struct LegendSwatch: View {
    let color: Color
    let label: String

    var body: some View {
        HStack(spacing: 5) {
            Rectangle().fill(color).frame(width: 8, height: 8)
            Text(label).font(JFFont.mono(10)).foregroundStyle(JF.ink2)
        }
    }
}

/// Spending per period, stacked by category, in fixed series order.
struct StackedSpendingChart: View {
    let spending: Spending
    var height: CGFloat = 210

    private struct Cell: Identifiable {
        let period: String
        let key: String
        let value: Double
        var id: String { period + key }
    }

    var body: some View {
        let labels = spending.series.map { Category.label($0.key) }
        let colors = spending.series.indices.map { i in spending.series[i].key == "OTHER" ? JF.other : JF.seriesColor(i) }
        let cells: [Cell] = spending.series.flatMap { s in
            s.numbers.enumerated().compactMap { i, v in
                i < spending.periods.count ? Cell(period: spending.periods[i].period, key: Category.label(s.key), value: v) : nil
            }
        }
        Chart(cells) { c in
            BarMark(x: .value("Period", c.period), y: .value("Amount", c.value), width: .ratio(0.7))
                .foregroundStyle(by: .value("Category", c.key))
        }
        .chartForegroundStyleScale(domain: labels, range: colors)
        .chartLegend(.hidden)
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

/// Assets above the line and debts below it, per month, stacked by kind.
struct ClassBarsChart: View {
    let data: NetWorthByClass
    var height: CGFloat = 230

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
            data.groups.compactMap { g in
                Fmt.day(p["date"]?.string).map { Cell(date: $0, label: g.label, value: (g.liability ? -1 : 1) * data.value(p, g.key)) }
            }
        }
        Chart(cells) { c in
            BarMark(x: .value("Month", c.date, unit: .month), y: .value("Amount", c.value), width: .ratio(0.75))
                .foregroundStyle(by: .value("Kind", c.label))
        }
        .chartForegroundStyleScale(domain: labels, range: colors)
        .chartLegend(position: .bottom, alignment: .leading, spacing: 8)
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
    }
}
