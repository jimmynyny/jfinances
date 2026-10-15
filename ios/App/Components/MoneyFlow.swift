import JFinancesKit
import SwiftUI

/// One end of the money-flow diagram: a source of income or a use of it.
struct FlowNodeSpec: Identifiable {
    let key: String
    let label: String
    let value: Double
    let color: Color
    /// Opens what the node is made of; nil when it opens nothing.
    var open: (() -> Void)?
    var id: String { key }
}

/// The diagram's geometry (packages/ui FlowChart, same constants): label columns
/// as wide as their longest name or amount needs, up to a share of the width; a
/// long name wraps onto two lines; both sides share one scale.
private struct FlowPlot {
    struct Node {
        let spec: FlowNodeSpec
        let y: CGFloat
        let h: CGFloat
        let lines: [String]
        var labelH: CGFloat { CGFloat(lines.count + 1) * FlowPlot.line + FlowPlot.air }
    }

    struct Ribbon {
        let key: String
        let path: Path
        let color: Color
    }

    static let nodeW: CGFloat = 10, gap: CGFloat = 6, pad: CGFloat = 6, top: CGFloat = 34
    static let line: CGFloat = 13, air: CGFloat = 5, ch: CGFloat = 7.2
    static let sideMax: CGFloat = 0.38, midMin: CGFloat = 88, midFloor: CGFloat = 56

    var height: CGFloat = 0
    var left: [Node] = []
    var right: [Node] = []
    var x0: CGFloat = 0, x1: CGFloat = 0, x2: CGFloat = 0, cy: CGFloat = 0, centerH: CGFloat = 0
    var ins: [Ribbon] = []
    var outs: [Ribbon] = []
    var total = 0.0
    var ly: [CGFloat] = []
    var ry: [CGFloat] = []

    static func money(_ v: Double) -> String { Fmt.money(v, cents: false) }

    /// `label` in at most two lines of `max` characters; a word too long for a line is cut with an ellipsis.
    static func fit(_ label: String, _ max: Int) -> [String] {
        func cut(_ s: String) -> String { s.count <= max ? s : String(s.prefix(Swift.max(1, max - 1))) + "…" }
        if label.count <= max { return [label] }
        let chars = Array(label)
        let spaces = chars.indices.filter { chars[$0] == " " && $0 <= max }
        guard !spaces.isEmpty else { return [cut(label)] }
        let mid = Double(chars.count) / 2
        let at = spaces.min { abs(Double($0) - mid) < abs(Double($1) - mid) }!
        return [String(chars[..<at]), cut(String(chars[(at + 1)...]))]
    }

    init() {}

    init(sources: [FlowNodeSpec], uses: [FlowNodeSpec], width: CGFloat, minHeight: CGFloat) {
        let l = sources.filter { $0.value > 0 }
        let r = uses.filter { $0.value > 0 }
        func sum(_ ns: [FlowNodeSpec]) -> Double { ns.reduce(0) { $0 + $1.value } }
        total = Swift.max(sum(l), sum(r))
        func need(_ ns: [FlowNodeSpec]) -> CGFloat {
            CGFloat(ns.reduce(0) { Swift.max($0, $1.label.count, Self.money($1.value).count) }) * Self.ch + 10
        }
        let sideMax = Swift.max(64, Swift.min(width * Self.sideMax, (width - Self.midMin) / 2))
        var lw = Swift.min(need(l), sideMax)
        var rw = Swift.min(need(r), sideMax)
        let spare = width - Self.midMin - lw - rw
        if spare > 0 {  // give room back to a side that wanted more, before the ribbons widen
            let wantL = need(l) - lw, wantR = need(r) - rw
            lw += Swift.min(wantL, spare / 2 + Swift.max(0, spare / 2 - wantR))
            rw += Swift.min(wantR, spare / 2 + Swift.max(0, spare / 2 - wantL))
        }
        // A label can wrap at spaces, but a single long word needs its whole width.
        func word(_ ns: [FlowNodeSpec]) -> CGFloat {
            CGFloat(ns.reduce(0) { m, n in Swift.max(m, n.label.split(separator: " ").map(\.count).max() ?? 0) }) * Self.ch + 10
        }
        lw = Swift.max(lw, Swift.min(word(l), width - rw - Self.midFloor))
        rw = Swift.max(rw, Swift.min(word(r), width - lw - Self.midFloor))
        func chars(_ w: CGFloat) -> Int { Swift.max(4, Int(((w - 10) / Self.ch).rounded(.down))) }
        let lLines = l.map { Self.fit($0.label, chars(lw)) }
        let rLines = r.map { Self.fit($0.label, chars(rw)) }
        func stack(_ ls: [[String]]) -> CGFloat { ls.reduce(0) { $0 + CGFloat($1.count + 1) * Self.line + Self.air } }
        // Tall enough for every label to have its own lines.
        height = Swift.max(minHeight, Self.top + Self.pad + Swift.max(stack(lLines), stack(rLines)))
        let usable = height - Self.top - Self.pad
        func room(_ n: Int) -> CGFloat { usable - Self.gap * CGFloat(Swift.max(0, n - 1)) }
        let scale = total > 0 ? Swift.max(0, Swift.min(room(l.count), room(r.count))) / CGFloat(total) : 0
        func place(_ ns: [FlowNodeSpec], _ ls: [[String]]) -> [Node] {
            var y = Self.top + (usable - (CGFloat(sum(ns)) * scale + Self.gap * CGFloat(Swift.max(0, ns.count - 1)))) / 2
            return ns.enumerated().map { i, n in
                let node = Node(spec: n, y: y, h: Swift.max(1, CGFloat(n.value) * scale), lines: ls[i])
                y += node.h + Self.gap
                return node
            }
        }
        left = place(l, lLines)
        right = place(r, rLines)
        x0 = lw
        x2 = Swift.max(x0 + Self.nodeW * 4, width - rw - Self.nodeW)
        x1 = (x0 + x2) / 2
        centerH = CGFloat(total) * scale
        cy = Self.top + (usable - centerH) / 2
        var off: CGFloat = 0
        ins = left.map { n in
            defer { off += n.h }
            return Ribbon(key: n.spec.key, path: Self.ribbon(x0 + Self.nodeW, n.y, x1, cy + off, n.h), color: n.spec.color)
        }
        off = 0
        outs = right.map { n in
            defer { off += n.h }
            return Ribbon(key: n.spec.key, path: Self.ribbon(x1 + Self.nodeW, cy + off, x2, n.y, n.h), color: n.spec.color)
        }
        ly = Self.labelYs(left, Self.top, height - Self.pad)
        ry = Self.labelYs(right, Self.top, height - Self.pad)
    }

    /// A filled band from (xa, ya..ya+h) to (xb, yb..yb+h).
    static func ribbon(_ xa: CGFloat, _ ya: CGFloat, _ xb: CGFloat, _ yb: CGFloat, _ h: CGFloat) -> Path {
        let mx = (xa + xb) / 2
        var p = Path()
        p.move(to: CGPoint(x: xa, y: ya))
        p.addCurve(to: CGPoint(x: xb, y: yb), control1: CGPoint(x: mx, y: ya), control2: CGPoint(x: mx, y: yb))
        p.addLine(to: CGPoint(x: xb, y: yb + h))
        p.addCurve(to: CGPoint(x: xa, y: ya + h), control1: CGPoint(x: mx, y: yb + h), control2: CGPoint(x: mx, y: ya + h))
        p.closeSubpath()
        return p
    }

    /// Label baselines beside their nodes: centred on the node, pushed apart top-down
    /// where thin nodes would collide, then pulled back up so the last stays inside.
    static func labelYs(_ nodes: [Node], _ top: CGFloat, _ bottom: CGFloat) -> [CGFloat] {
        var ys = nodes.map { $0.y + $0.h / 2 - $0.labelH / 2 + 10 }
        for i in ys.indices { ys[i] = Swift.max(ys[i], i == 0 ? top + 10 : ys[i - 1] + nodes[i - 1].labelH) }
        for i in ys.indices.reversed() {
            ys[i] = Swift.min(ys[i], i == ys.count - 1 ? bottom - nodes[i].labelH + 10 : ys[i + 1] - nodes[i].labelH)
        }
        return ys
    }
}

/// Money flow, a two-stage Sankey: sources on the left join into one middle
/// node, which splits into uses on the right; a ribbon's width is its amount and
/// every amount is in the labels. The first tap lights a path, the second opens
/// its transactions (the web on a touch screen).
struct MoneyFlowChart: View {
    let sources: [FlowNodeSpec]
    let uses: [FlowNodeSpec]
    let centerLabel: String
    var minHeight: CGFloat = 320
    var openCenter: (() -> Void)?
    @State private var width: CGFloat = 0
    @State private var lit: String?

    var body: some View {
        let plot = width > 0 ? FlowPlot(sources: sources, uses: uses, width: width, minHeight: minHeight) : FlowPlot()
        ZStack(alignment: .topLeading) {
            if plot.total > 0 {
                Canvas { ctx, _ in
                    for r in plot.ins + plot.outs {
                        let o = dim(r.key) ? 0.08 : lit == r.key ? 0.5 : 0.28
                        ctx.fill(r.path, with: .color(r.color.opacity(o)))
                    }
                    for (n, x) in plot.left.map({ ($0, plot.x0) }) + plot.right.map({ ($0, plot.x2) }) {
                        ctx.fill(Path(CGRect(x: x, y: n.y, width: FlowPlot.nodeW, height: n.h)), with: .color(n.spec.color))
                    }
                    ctx.fill(Path(CGRect(x: plot.x1, y: plot.cy, width: FlowPlot.nodeW, height: plot.centerH)), with: .color(JF.ink2))
                }
                VStack(spacing: 0) {
                    Text(centerLabel).font(JFFont.mono(12)).foregroundStyle(JF.ink).frame(height: FlowPlot.line)
                    Text(FlowPlot.money(plot.total)).font(JFFont.mono(12)).foregroundStyle(JF.ink3).frame(height: FlowPlot.line).figure(size: 12)
                }
                .frame(width: 140)
                .offset(x: plot.x1 + FlowPlot.nodeW / 2 - 70, y: 2)
                ForEach(Array(plot.left.enumerated()), id: \.element.spec.key) { i, n in
                    label(n, alignment: .trailing)
                        .frame(width: Swift.max(0, plot.x0 - 8), alignment: .trailing)
                        .offset(x: 0, y: plot.ly[i] - 10)
                }
                ForEach(Array(plot.right.enumerated()), id: \.element.spec.key) { i, n in
                    let x = plot.x2 + FlowPlot.nodeW + 8
                    label(n, alignment: .leading)
                        .frame(width: Swift.max(0, width - x), alignment: .leading)
                        .offset(x: x, y: plot.ry[i] - 10)
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .topLeading)
        .frame(height: plot.total > 0 ? plot.height : minHeight)
        .background(GeometryReader { g in Color.clear.onAppear { width = g.size.width }.onChange(of: g.size.width) { _, w in width = w } })
        .contentShape(Rectangle())
        .onTapGesture(coordinateSpace: .local) { p in tap(p, plot) }
        .accessibilityElement(children: .combine)
        .accessibilityLabel("Money flow from income to spending")
    }

    private func dim(_ key: String) -> Bool { lit != nil && lit != key && lit != "center" }

    private func label(_ n: FlowPlot.Node, alignment: HorizontalAlignment) -> some View {
        VStack(alignment: alignment, spacing: 0) {
            ForEach(Array(n.lines.enumerated()), id: \.offset) { _, line in
                Text(line).font(JFFont.mono(12)).foregroundStyle(JF.ink).lineLimit(1).frame(height: FlowPlot.line)
            }
            Text(FlowPlot.money(n.spec.value)).font(JFFont.mono(12)).foregroundStyle(JF.ink3).lineLimit(1)
                .frame(height: FlowPlot.line).figure(size: 12)
        }
        .opacity(dim(n.spec.key) ? 0.35 : 1)
    }

    /// Labels, nodes and the middle first (the easy targets), then the ribbons.
    private func tap(_ p: CGPoint, _ plot: FlowPlot) {
        var hit: (String, (() -> Void)?)?
        for (i, n) in plot.left.enumerated() where hit == nil {
            let label = CGRect(x: 0, y: plot.ly[i] - 11, width: plot.x0 - 4, height: n.labelH - FlowPlot.air)
            let node = CGRect(x: plot.x0 - 6, y: n.y, width: FlowPlot.nodeW + 12, height: n.h)
            if label.contains(p) || node.contains(p) { hit = (n.spec.key, n.spec.open) }
        }
        for (i, n) in plot.right.enumerated() where hit == nil {
            let x = plot.x2 + FlowPlot.nodeW + 4
            let label = CGRect(x: x, y: plot.ry[i] - 11, width: width - x, height: n.labelH - FlowPlot.air)
            let node = CGRect(x: plot.x2 - 6, y: n.y, width: FlowPlot.nodeW + 12, height: n.h)
            if label.contains(p) || node.contains(p) { hit = (n.spec.key, n.spec.open) }
        }
        if hit == nil {
            let center = CGRect(x: plot.x1 + FlowPlot.nodeW / 2 - 60, y: 0, width: 120, height: 30)
            let node = CGRect(x: plot.x1 - 6, y: plot.cy, width: FlowPlot.nodeW + 12, height: plot.centerH)
            if center.contains(p) || node.contains(p) { hit = ("center", openCenter) }
        }
        if hit == nil {
            let nodes = Dictionary(uniqueKeysWithValues: (plot.left + plot.right).map { ($0.spec.key, $0.spec.open) })
            if let r = (plot.ins + plot.outs).first(where: { $0.path.contains(p) }) { hit = (r.key, nodes[r.key] ?? nil) }
        }
        guard let (key, open) = hit else { lit = nil; return }
        if lit == key, let open {
            lit = nil
            open()
        } else {
            lit = key
        }
    }
}
