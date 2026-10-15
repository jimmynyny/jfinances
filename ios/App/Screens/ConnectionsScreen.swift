import JFinancesKit
import SwiftUI

/// The household's bank connections, as the dashboard's Settings → connections:
/// each with its status and last sync; sync one or all now, connect a new bank,
/// re-link or add accounts to one, unlink one. Offline accounts are added here
/// too. Connecting runs Plaid Link in the app (docs/30 "Link on the phones").
struct ConnectionsScreen: View {
    @Environment(AppModel.self) private var model
    @State private var toast: String?
    @State private var busy: String?
    @State private var removing: Item?
    @State private var adding = false

    var body: some View {
        Screen("Connections", inline: true) {
            HStack(spacing: 10) {
                Button {
                    Task { await run("sync") { try await APIClient.shared.syncAll(); return "Sync queued for every connection" } }
                } label: {
                    HStack(spacing: 6) {
                        if busy == "sync" { ProgressView() }
                        Text("Sync everything")
                    }
                }
                .buttonStyle(QuietButtonStyle())
                .disabled(busy != nil)
                Button {
                    Task { await run("prices") { try await APIClient.shared.refreshPrices() ? "Market prices refreshing" : "Prices already refreshing" } }
                } label: {
                    HStack(spacing: 6) {
                        if busy == "prices" { ProgressView() }
                        Text("Refresh prices")
                    }
                }
                .buttonStyle(QuietButtonStyle())
                .disabled(busy != nil)
            }
            ConnectBankButton { toast = $0 }
            Loader(height: 240) {
                try await APIClient.shared.items()
            } content: { items in
                let live = items.filter { $0.status != "removed" }
                Panel("connections", flush: true, actions: { Fine("\(live.count) linked") }) {
                    if live.isEmpty { Fine("No connections yet. Connect a bank, card, loan or brokerage.").padding(16) }
                    RuledList(live) { item in row(item) }
                }
            }
            Button("Add an offline account") { adding = true }
                .buttonStyle(QuietButtonStyle())
            Fine("An offline account is one no bank reports: a home, a car, cash, another asset or another debt. Its value is what you enter, or a monthly market estimate for a home or car.")
        }
        .toast($toast)
        .sheet(isPresented: $adding) {
            AddOfflineSheet { a in toast = "Added \(a.name)" }
        }
        .confirmationDialog("Unlink \(removing?.name ?? "this connection")?", isPresented: Binding(get: { removing != nil }, set: { if !$0 { removing = nil } }), titleVisibility: .visible) {
            Button("Unlink", role: .destructive) {
                if let item = removing {
                    Task { await run("remove-\(item.id)") { _ = try await APIClient.shared.removeItem(id: item.id); return "Unlinked \(item.name)" } }
                }
            }
        } message: {
            if let item = removing {
                Text("This disconnects \(item.name) and ends its monthly connection fee. Its \(item.account_count ?? 0) accounts and their history stay but stop updating. Connecting it again later starts a new connection, billed again; to change which accounts it covers, use Add accounts instead.")
            }
        }
    }

    private func row(_ item: Item) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .top, spacing: 10) {
                VStack(alignment: .leading, spacing: 4) {
                    HStack(spacing: 6) {
                        Text(item.name).font(JFFont.sans(15, .medium)).foregroundStyle(JF.ink).lineLimit(1)
                        Fine("· \(item.account_count ?? 0) account\(item.account_count == 1 ? "" : "s")")
                    }
                    HStack(spacing: 6) {
                        Badge(item.statusLabel + (item.error_code.map { " · \($0)" } ?? ""), tone: tone(item.status))
                        if item.new_accounts_at != nil { Badge("new accounts available", tone: .accent) }
                    }
                    if let msg = item.error_message, !msg.isEmpty { Fine(msg) }
                    if let ts = item.transactions_status, ts != "HISTORICAL_UPDATE_COMPLETE" {
                        Fine("history still loading (\(ts.lowercased().replacingOccurrences(of: "_", with: " ")))")
                    }
                    Fine("synced \(Fmt.relative(item.last_synced_at)) · \((item.products ?? []).joined(separator: ", "))")
                }
                Spacer(minLength: 8)
                if busy == "sync-\(item.id)" || busy == "remove-\(item.id)" { ProgressView() }
            }
            HStack(spacing: 8) {
                Button("Sync now") {
                    Task { await run("sync-\(item.id)") { try await APIClient.shared.syncItem(id: item.id) ? "Sync queued" : "Sync already queued" } }
                }
                .buttonStyle(SmallButtonStyle())
                RelinkButton(item: item) { toast = $0 }
                Spacer()
                Button("Unlink") { removing = item }
                    .buttonStyle(SmallButtonStyle(destructive: true))
            }
        }
        .padding(.vertical, 12)
    }

    private func tone(_ status: String) -> Badge.Tone {
        switch status {
        case "active": return .good
        case "login_required", "pending_expiration": return .warn
        case "error": return .bad
        default: return .neutral
        }
    }

    private func run(_ key: String, _ work: @escaping () async throws -> String) async {
        busy = key
        defer { busy = nil }
        do {
            toast = try await work()
            model.changed()
        } catch let e as APIError {
            model.handle(e)
            toast = e.errorDescription
        } catch {
            toast = error.localizedDescription
        }
    }
}

/// A small quiet button for a row's actions.
struct SmallButtonStyle: ButtonStyle {
    var destructive = false
    var primary = false

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(JFFont.mono(12, .medium))
            .foregroundStyle(primary ? JF.accentInk : destructive ? JF.neg : JF.ink)
            .padding(.horizontal, 10)
            .frame(height: 30)
            .background(primary ? JF.accent : configuration.isPressed ? JF.panel2 : JF.panel)
            .overlay(Rectangle().strokeBorder(primary ? JF.accent : JF.line, lineWidth: 1))
    }
}
