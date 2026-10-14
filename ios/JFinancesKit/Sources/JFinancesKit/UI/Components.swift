import SwiftUI

// The design system's building blocks (packages/ui), redrawn for SwiftUI.

/// A mono caption led by the accent square: `■ net worth`.
public struct Caption: View {
    let text: String
    public init(_ text: String) { self.text = text }

    public var body: some View {
        HStack(spacing: 8) {
            Rectangle().fill(JF.accent).frame(width: 6, height: 6)
            Text(text).font(JFFont.mono(12, relativeTo: .caption)).foregroundStyle(JF.ink2)
        }
    }
}

/// A panel: square corners, a 1px rule, a caption row with its own rule.
public struct Panel<Content: View, Actions: View>: View {
    let caption: String?
    let flush: Bool
    let actions: Actions
    let content: Content

    public init(_ caption: String? = nil, flush: Bool = false, @ViewBuilder actions: () -> Actions,
                @ViewBuilder content: () -> Content) {
        self.caption = caption
        self.flush = flush
        self.actions = actions()
        self.content = content()
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            if let caption {
                HStack(spacing: 12) {
                    Caption(caption)
                    Spacer(minLength: 0)
                    actions
                }
                .padding(.horizontal, 16)
                .frame(minHeight: 40)
                Rectangle().fill(JF.line).frame(height: 1)
            }
            content
                .padding(flush ? 0 : 16)
                .frame(maxWidth: .infinity, alignment: .leading)
        }
        .background(JF.panel)
        .overlay(Rectangle().strokeBorder(JF.line, lineWidth: 1))
    }
}

public extension Panel where Actions == EmptyView {
    init(_ caption: String? = nil, flush: Bool = false, @ViewBuilder content: () -> Content) {
        self.init(caption, flush: flush, actions: { EmptyView() }, content: content)
    }
}

/// The LED readout: the one hero figure per screen, in the dot-matrix face.
public struct Readout: View {
    let label: String?
    let value: String
    let unit: String?
    let size: CGFloat
    let delta: AnyView?

    public init(_ label: String? = nil, value: String, unit: String? = nil, size: CGFloat = 48, delta: AnyView? = nil) {
        self.label = label
        self.value = value
        self.unit = unit
        self.size = size
        self.delta = delta
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            if let label {
                Text(label).font(JFFont.mono(12, relativeTo: .caption)).foregroundStyle(JF.ink2)
            }
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                Text(value)
                    .font(JFFont.pixel(size))
                    .foregroundStyle(JF.ink)
                    .lineLimit(1)
                    .minimumScaleFactor(0.5)
                    .figure(size: size)
                if let unit {
                    Text(unit).font(JFFont.mono(12)).foregroundStyle(JF.ink3)
                }
            }
            if let delta { delta }
        }
    }
}

/// ▲ $1,234.00 (2.1%) label — green when good, red when bad.
public struct Delta: View {
    let amount: Double?
    let pct: Double?
    let label: String?
    let upIsGood: Bool
    let cents: Bool
    let size: CGFloat

    /// `pct` is a percent (2.1 means 2.1%), as the server sends change_1m.
    public init(amount: Double?, pct: Double? = nil, label: String? = nil, upIsGood: Bool = true, cents: Bool = false,
                size: CGFloat = 12) {
        self.amount = amount
        self.pct = pct
        self.label = label
        self.upIsGood = upIsGood
        self.cents = cents
        self.size = size
    }

    public var body: some View {
        let basis = amount ?? pct ?? 0
        let up = basis > 0
        let flat = basis == 0
        let good = flat ? nil : (up == upIsGood)
        let color = good == nil ? JF.ink3 : (good! ? JF.pos : JF.neg)
        HStack(spacing: 5) {
            Text(flat ? "—" : up ? "▲" : "▼").font(.system(size: size * 0.8))
            Group {
                if let amount { Text(Fmt.money(abs(amount), cents: cents)) }
                if let pct { Text("(\(Fmt.pct(abs(pct), ratio: false)))") }
            }
            .figure(size: size)
            if let label { Text(label).foregroundStyle(JF.ink3) }
        }
        .font(JFFont.mono(size, .medium))
        .foregroundStyle(color)
    }
}

/// Money in Plex Mono, tabular, blurred with the switch.
public struct MoneyText: View {
    public enum Style { case plain, signed, flow }
    let value: Double
    let cents: Bool
    let style: Style
    let size: CGFloat
    let weight: JFFont.Weight
    let currency: String

    /// `flow` takes Plaid's sign (positive = money out) and shows money in as
    /// +green, money out as plain.
    public init(_ value: Double, cents: Bool = true, style: Style = .plain, size: CGFloat = 14,
                weight: JFFont.Weight = .regular, currency: String = "USD") {
        self.value = value
        self.cents = cents
        self.style = style
        self.size = size
        self.weight = weight
        self.currency = currency
    }

    public var body: some View {
        let text: String
        var color = JF.ink
        switch style {
        case .plain: text = Fmt.money(value, cents: cents, currency: currency)
        case .signed:
            text = Fmt.signed(value, cents: cents, currency: currency)
            color = value > 0 ? JF.pos : value < 0 ? JF.neg : JF.ink
        case .flow:
            if value < 0 {
                text = "+" + Fmt.money(-value, cents: cents, currency: currency)
                color = JF.pos
            } else {
                text = Fmt.money(value, cents: cents, currency: currency)
            }
        }
        return Text(text)
            .font(JFFont.mono(size, weight))
            .monospacedDigit()
            .foregroundStyle(color)
            .lineLimit(1)
            .fixedSize(horizontal: true, vertical: false)
            .layoutPriority(1)
            .figure(size: size)
    }
}

/// A labelled figure for grids of three.
public struct StatTile: View {
    let label: String
    let value: AnyView
    let note: String?

    public init(_ label: String, note: String? = nil, @ViewBuilder value: () -> some View) {
        self.label = label
        self.note = note
        self.value = AnyView(value())
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(label).font(JFFont.mono(11, relativeTo: .caption)).foregroundStyle(JF.ink3)
            value
            if let note { Text(note).font(JFFont.mono(11, relativeTo: .caption2)).foregroundStyle(JF.ink3) }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

/// A key/value list: the key in mono, the value trailing.
public struct KeyValueRow<V: View>: View {
    let key: String
    let value: V

    public init(_ key: String, @ViewBuilder value: () -> V) {
        self.key = key
        self.value = value()
    }

    public var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 12) {
            Text(key).font(JFFont.mono(12, relativeTo: .caption)).foregroundStyle(JF.ink3)
            Spacer(minLength: 8)
            value.font(JFFont.sans(14)).foregroundStyle(JF.ink).multilineTextAlignment(.trailing)
        }
        .padding(.vertical, 6)
    }
}

public struct Badge: View {
    public enum Tone { case neutral, good, warn, bad, accent }
    let text: String
    let tone: Tone

    public init(_ text: String, tone: Tone = .neutral) {
        self.text = text
        self.tone = tone
    }

    public var body: some View {
        HStack(spacing: 5) {
            Circle().fill(dot).frame(width: 6, height: 6)
            Text(text).font(JFFont.mono(11)).foregroundStyle(JF.ink2).lineLimit(1)
        }
        .fixedSize()
        .padding(.horizontal, 6)
        .padding(.vertical, 2)
        .background(JF.panel)
        .overlay(RoundedRectangle(cornerRadius: 2).strokeBorder(JF.line, lineWidth: 1))
    }

    private var dot: Color {
        switch tone {
        case .neutral: return JF.ink3
        case .good: return JF.good
        case .warn: return JF.warn
        case .bad: return JF.critical
        case .accent: return JF.accent
        }
    }
}

/// A 1px rule in the line colour.
public struct Rule: View {
    public init() {}
    public var body: some View { Rectangle().fill(JF.line).frame(height: 1) }
}
