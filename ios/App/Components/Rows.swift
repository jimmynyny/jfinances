import JFinancesKit
import SwiftUI

/// An account: name, institution ··last4, balance, and a dot-matrix trend.
struct AccountRow: View {
    let account: Account
    /// The line beside the balance; a wide screen's narrow list leaves it out for the name.
    var trend = true

    var body: some View {
        HStack(spacing: 12) {
            VStack(alignment: .leading, spacing: 3) {
                HStack(spacing: 6) {
                    Text(account.name).font(JFFont.sans(15, .medium)).foregroundStyle(JF.ink).lineLimit(1)
                    if account.is_business == true { BusinessMark() }
                }
                Text(account.subtitle).font(JFFont.mono(11)).foregroundStyle(JF.ink3).lineLimit(1)
            }
            Spacer(minLength: 8)
            if trend, account.trendValues.count >= 2 {
                PixelSparkline(account.trendValues).frame(width: 54, height: 18)
            }
            MoneyText(account.balance, cents: false, size: 15, weight: .medium, currency: account.currency)
        }
        .padding(.vertical, 10)
        .contentShape(Rectangle())
    }
}

/// A transaction: category glyph, merchant, category · account, amount (and
/// its date, in a list that isn't grouped by day).
struct TxnRow: View {
    let tx: Txn
    var showAccount = true
    var showDate = false

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: Category.symbol(tx.category == "PAYMENT" ? "PAYMENT" : tx.category_primary))
                .font(.system(size: 13, weight: .medium))
                .foregroundStyle(JF.ink2)
                .frame(width: 30, height: 30)
                .background(JF.panel2)
                .overlay(Rectangle().strokeBorder(JF.line, lineWidth: 1))
            VStack(alignment: .leading, spacing: 3) {
                HStack(spacing: 6) {
                    Text(tx.title).font(JFFont.sans(15, .medium)).foregroundStyle(JF.ink).lineLimit(1)
                    if tx.is_business == true { BusinessMark() }
                    if tx.pending { Badge("pending", tone: .warn) }
                }
                Text(subtitle).font(JFFont.mono(11)).foregroundStyle(JF.ink3).lineLimit(1)
            }
            Spacer(minLength: 8)
            MoneyText(tx.amount, style: .flow, size: 15, weight: .medium, currency: tx.currency)
        }
        .padding(.vertical, 9)
        .contentShape(Rectangle())
    }

    private var subtitle: String {
        var parts = [Category.label(tx.category)]
        if showDate { parts.insert(Fmt.date(tx.date), at: 0) }
        if showAccount, let name = tx.account_name {
            parts.append(name + (tx.account_mask.map { " ··\($0)" } ?? ""))
        }
        return parts.joined(separator: " · ")
    }
}

/// An expected charge: when, what, how much.
struct UpcomingRow: View {
    let item: UpcomingCharge

    var body: some View {
        HStack(spacing: 12) {
            VStack(alignment: .leading, spacing: 0) {
                Text(dayLabel).font(JFFont.mono(11, .medium)).foregroundStyle(item.overdue ? JF.neg : JF.ink2)
            }
            .frame(width: 64, alignment: .leading)
            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 6) {
                    Text(item.label).font(JFFont.sans(14, .medium)).foregroundStyle(JF.ink).lineLimit(1)
                    if item.is_business == true { BusinessMark() }
                }
                Text([item.cadence, item.account_name].compactMap { $0 }.joined(separator: " · "))
                    .font(JFFont.mono(11)).foregroundStyle(JF.ink3).lineLimit(1)
            }
            Spacer(minLength: 8)
            MoneyText(item.amount, size: 14, weight: .medium)
        }
        .padding(.vertical, 8)
    }

    private var dayLabel: String {
        switch Fmt.daysUntil(item.date) {
        case 0: return item.overdue ? "due" : "today"
        case 1: return "tomorrow"
        default: return Fmt.date(item.date)
        }
    }
}

/// An alert, in words: what happened and by how much.
struct AlertRow: View {
    let alert: MoneyAlert

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: symbol)
                .font(.system(size: 13, weight: .semibold))
                .foregroundStyle(JF.accent)
                .frame(width: 30, height: 30)
                .background(JF.accentWash)
            VStack(alignment: .leading, spacing: 3) {
                Text(alert.merchant).font(JFFont.sans(14, .medium)).foregroundStyle(JF.ink).lineLimit(1)
                Text(explanation).font(JFFont.sans(13)).foregroundStyle(JF.ink2).figure(size: 13)
                Text(Fmt.date(alert.date)).font(JFFont.mono(11)).foregroundStyle(JF.ink3)
            }
            Spacer(minLength: 8)
            MoneyText(alert.amount, size: 14, weight: .medium)
        }
        .padding(.vertical, 8)
    }

    private var symbol: String {
        switch alert.kind {
        case "price": return "arrow.up.right"
        case "duplicate": return "square.on.square"
        default: return "exclamationmark"
        }
    }

    private var explanation: String {
        switch alert.kind {
        case "price":
            if let prev = alert.previous { return "Price went from \(Fmt.money(prev)) to \(Fmt.money(alert.amount))." }
            return "The price changed."
        case "duplicate": return "Charged twice within two days."
        default:
            if let usual = alert.usual {
                return alert.basis == "category"
                    ? "Far above the usual \(Category.label(alert.category)) charge of \(Fmt.money(usual))."
                    : "Far above the usual \(Fmt.money(usual)) here."
            }
            return "Larger than usual."
        }
    }
}

/// A category with its share of the total as a meter.
struct ShareRow: View {
    let label: String
    let amount: Double
    let share: Double
    let tone: PixelMeter.Tone

    var body: some View {
        VStack(alignment: .leading, spacing: 5) {
            HStack {
                Text(label).font(JFFont.sans(14)).foregroundStyle(JF.ink).lineLimit(1)
                Spacer(minLength: 8)
                MoneyText(amount, cents: false, size: 13)
                Text(Fmt.pct(share, digits: 0)).font(JFFont.mono(11)).foregroundStyle(JF.ink3).frame(width: 38, alignment: .trailing)
                    .figure(size: 11)
            }
            PixelMeter(ratio: share, cells: 32, tone: tone, height: 6)
        }
        .padding(.vertical, 4)
    }
}

/// Rows separated by 1px rules, inside a flush panel.
extension View {
    /// A row picked in a wide screen's list: the accent wash edge to edge of a
    /// `RuledList` row, and a bar at its left.
    func picked(_ on: Bool) -> some View {
        background {
            if on {
                JF.accentWash.padding(.horizontal, -16)
                    .overlay(alignment: .leading) { JF.accent.frame(width: 3).offset(x: -16) }
            }
        }
    }
}

struct RuledList<Item: Identifiable, Row: View>: View {
    let items: [Item]
    let row: (Item) -> Row

    init(_ items: [Item], @ViewBuilder row: @escaping (Item) -> Row) {
        self.items = items
        self.row = row
    }

    var body: some View {
        VStack(spacing: 0) {
            ForEach(Array(items.enumerated()), id: \.element.id) { i, item in
                row(item).padding(.horizontal, 16)
                if i < items.count - 1 { Rule().padding(.leading, 16) }
            }
        }
    }
}
