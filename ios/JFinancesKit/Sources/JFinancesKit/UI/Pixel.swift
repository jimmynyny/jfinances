import SwiftUI

// The pixel layer (docs/70): square cells with a gap, each one lit or off.

public enum Cells {
    /// Average values into `n` buckets, oldest to newest; the last bucket
    /// keeps the true last value.
    public static func downsample(_ values: [Double], _ n: Int) -> [Double] {
        let finite = values.filter(\.isFinite)
        guard finite.count > n, n > 0 else { return finite }
        var out: [Double] = []
        for b in 0..<n {
            let lo = (b * finite.count) / n
            let hi = max(lo + 1, ((b + 1) * finite.count) / n)
            out.append(finite[lo..<hi].reduce(0, +) / Double(hi - lo))
        }
        out[out.count - 1] = finite[finite.count - 1]
        return out
    }

    /// Split `total` cells across shares so they sum exactly (largest
    /// remainder); a positive share never rounds to nothing while a larger
    /// one can spare a cell.
    public static func allocate(_ shares: [Double], _ total: Int) -> [Int] {
        let pos = shares.map { $0.isFinite && $0 > 0 ? $0 : 0 }
        let sum = pos.reduce(0, +)
        guard sum > 0, total > 0 else { return pos.map { _ in 0 } }
        let exact = pos.map { $0 / sum * Double(total) }
        var counts = exact.map { Int($0.rounded(.down)) }
        var left = total - counts.reduce(0, +)
        let order = exact.enumerated().sorted { ($0.element - $0.element.rounded(.down)) > ($1.element - $1.element.rounded(.down)) }
        var k = 0
        while left > 0 && k < order.count {
            counts[order[k].offset] += 1
            left -= 1
            k += 1
        }
        for i in counts.indices where pos[i] > 0 && counts[i] == 0 {
            if let donor = counts.indices.filter({ counts[$0] > 1 }).max(by: { counts[$0] < counts[$1] }) {
                counts[donor] -= 1
                counts[i] = 1
            }
        }
        return counts
    }
}

/// A tiny dot-matrix trend: one lit cell per column on the trace, dimmer
/// cells under it, the newest cell in the accent. Right-aligned.
public struct PixelSparkline: View {
    let values: [Double]
    let cell: CGFloat
    let gap: CGFloat
    let color: Color
    let fill: Bool

    public init(_ values: [Double], cell: CGFloat = 2, gap: CGFloat = 1, color: Color = JF.ink3, fill: Bool = true) {
        self.values = values
        self.cell = cell
        self.gap = gap
        self.color = color
        self.fill = fill
    }

    public var body: some View {
        Canvas { ctx, size in
            let pitch = cell + gap
            let cols = max(2, Int((size.width + gap) / pitch))
            let rows = max(3, Int((size.height + gap) / pitch))
            let v = Cells.downsample(values, cols)
            guard v.count >= 2, let lo = v.min(), let hi = v.max() else { return }
            let span = hi - lo
            func level(_ x: Double) -> Int { span == 0 ? (rows - 1) / 2 : Int(((x - lo) / span * Double(rows - 1)).rounded()) }
            let x0 = size.width - (CGFloat(v.count) * pitch - gap)
            let top = size.height - (CGFloat(rows) * pitch - gap)
            var trace = Path(), near = Path(), deep = Path()
            for (i, val) in v.enumerated() {
                let lv = level(val)
                let x = x0 + CGFloat(i) * pitch
                let rect = { (r: Int) in CGRect(x: x, y: top + CGFloat(rows - 1 - r) * pitch, width: cell, height: cell) }
                if i == v.count - 1 {
                    ctx.fill(Path(rect(lv)), with: .color(JF.accent))
                } else {
                    trace.addRect(rect(lv))
                }
                if fill && lv > 0 {
                    for r in stride(from: lv - 1, through: 0, by: -1) {
                        if lv - r <= 2 { near.addRect(rect(r)) } else { deep.addRect(rect(r)) }
                    }
                }
            }
            if fill {
                ctx.fill(deep, with: .color(color.opacity(0.16)))
                ctx.fill(near, with: .color(color.opacity(0.38)))
            }
            ctx.fill(trace, with: .color(color))
        }
        .accessibilityHidden(true)
    }
}

/// A meter of discrete cells: lit up to `ratio`, the rest a faint step of
/// the same colour.
public struct PixelMeter: View {
    public enum Tone { case accent, pos, neg, warn, ink, series(Int) }
    let ratio: Double
    let cells: Int
    let tone: Tone
    let height: CGFloat

    public init(ratio: Double, cells: Int = 24, tone: Tone = .accent, height: CGFloat = 8) {
        self.ratio = ratio
        self.cells = cells
        self.tone = tone
        self.height = height
    }

    var color: Color {
        switch tone {
        case .accent: return JF.accent
        case .pos: return JF.pos
        case .neg: return JF.neg
        case .warn: return JF.warn
        case .ink: return JF.ink2
        case .series(let i): return JF.seriesColor(i)
        }
    }

    public var body: some View {
        Canvas { ctx, size in
            let n = max(4, cells)
            let gap: CGFloat = height <= 6 ? 1 : 2
            let w = (size.width - gap * CGFloat(n - 1)) / CGFloat(n)
            let lit = Int((min(1, max(0, ratio)) * Double(n)).rounded())
            let litN = ratio > 0 ? max(1, lit) : 0
            for i in 0..<n {
                let r = CGRect(x: CGFloat(i) * (w + gap), y: 0, width: w, height: size.height)
                ctx.fill(Path(r), with: .color(i < litN ? color : color.opacity(0.16)))
            }
        }
        .frame(height: height)
        .accessibilityLabel("\(Int((ratio * 100).rounded())) percent")
    }
}

/// Vertical bars of stacked cells, one per value (downsampled to fit), the
/// newest in the accent. Negative values hang below a baseline in `negColor`.
public struct PixelBars: View {
    let values: [Double]
    let color: Color
    let negColor: Color
    let highlightLast: Bool

    public init(_ values: [Double], color: Color = JF.ink2, negColor: Color = JF.divNeg, highlightLast: Bool = true) {
        self.values = values
        self.color = color
        self.negColor = negColor
        self.highlightLast = highlightLast
    }

    public var body: some View {
        Canvas { ctx, size in
            let gap: CGFloat = 1
            let fit = max(1, Int((size.width + gap) / (2 + gap)))
            let v = values.count > fit ? Cells.downsample(values, fit) : values
            guard !v.isEmpty else { return }
            let n = v.count
            let cell = min(6, floor((size.width - gap * CGFloat(n - 1)) / CGFloat(n)))
            let pitch = cell + gap
            let x0 = size.width - (CGFloat(n) * pitch - gap)
            let rows = max(2, Int((size.height + gap) / pitch))
            let maxPos = max(v.max() ?? 0, 0)
            let maxNeg = max(-(v.min() ?? 0), 0)
            let span = maxPos + maxNeg
            guard span > 0 else { return }
            let posRows = maxNeg > 0 ? max(1, Int((Double(rows) * maxPos / span).rounded())) : rows
            let baseY = size.height - CGFloat(rows - posRows) * pitch
            for (i, val) in v.enumerated() where val != 0 {
                let lit = max(1, Int((abs(val) / span * Double(rows)).rounded()))
                let x = x0 + CGFloat(i) * pitch
                var p = Path()
                for r in 0..<lit {
                    let y = val > 0 ? baseY - CGFloat(r + 1) * pitch + gap : baseY + CGFloat(r) * pitch
                    p.addRect(CGRect(x: x, y: y, width: cell, height: cell))
                }
                let fill = (highlightLast && i == n - 1) ? JF.accent : (val < 0 ? negColor : color)
                ctx.fill(p, with: .color(fill))
            }
        }
        .accessibilityHidden(true)
    }
}

/// Part-to-whole as a grid of cells filled column by column, so each slice
/// reads as a band; a legend lists label, value and share.
public struct WaffleSlice: Identifiable, Hashable {
    public let key: String
    public let label: String
    public let value: Double
    public let color: Color
    public var id: String { key }

    public init(key: String, label: String, value: Double, color: Color) {
        self.key = key
        self.label = label
        self.value = value
        self.color = color
    }
}

public struct WaffleGrid: View {
    let slices: [WaffleSlice]
    let size: Int

    public init(_ slices: [WaffleSlice], size: Int = 10) {
        self.slices = slices
        self.size = size
    }

    public var body: some View {
        Canvas { ctx, box in
            let gap: CGFloat = 2
            let edge = min(box.width, box.height)
            let cell = (edge - gap * CGFloat(size - 1)) / CGFloat(size)
            let counts = Cells.allocate(slices.map(\.value), size * size)
            var i = 0
            for (si, s) in slices.enumerated() {
                var p = Path()
                for _ in 0..<counts[si] {
                    let col = i / size, row = i % size
                    p.addRect(CGRect(x: CGFloat(col) * (cell + gap), y: CGFloat(row) * (cell + gap), width: cell, height: cell))
                    i += 1
                }
                ctx.fill(p, with: .color(s.color))
            }
            var off = Path()
            while i < size * size {
                let col = i / size, row = i % size
                off.addRect(CGRect(x: CGFloat(col) * (cell + gap), y: CGFloat(row) * (cell + gap), width: cell, height: cell))
                i += 1
            }
            ctx.fill(off, with: .color(JF.pixelOff))
        }
        .aspectRatio(1, contentMode: .fit)
        .accessibilityHidden(true)
    }
}

/// Fold slices beyond `max` into "Other", keeping a stable colour per key.
public func waffleSlices(_ items: [(key: String, label: String, value: Double)], max: Int = 6) -> [WaffleSlice] {
    let positive = items.filter { $0.value > 0 }
    let colored = positive.enumerated().map { WaffleSlice(key: $1.key, label: $1.label, value: $1.value, color: JF.seriesColor($0)) }
    guard colored.count > max else { return colored }
    let keep = Set(colored.sorted { $0.value > $1.value }.prefix(max - 1).map(\.key))
    let kept = colored.filter { keep.contains($0.key) }
    let rest = colored.filter { !keep.contains($0.key) }
    return kept + [WaffleSlice(key: "__other", label: "other (\(rest.count))", value: rest.reduce(0) { $0 + $1.value }, color: JF.other)]
}
