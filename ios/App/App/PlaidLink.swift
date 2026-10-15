import JFinancesKit
import LinkKit
import SwiftUI
import UIKit

/// Plaid Link in the app (docs/30 "Link on the phones"): a link token from the
/// server (`platform: ios`), Link over the current screen, then the exchange
/// (a new connection, through the server's duplicate guard, which may ask a
/// question first) or update-complete (a re-link, or adding accounts). An OAuth
/// bank's return is a universal link on the API hostname, which LinkKit handles
/// on its own; the phone never sees an access token.
@MainActor
@Observable
final class LinkFlow {
    /// The duplicate guard's 409: nothing was exchanged, so nothing is billed,
    /// until the answer is yes. `confirm` is the answer that lets it through,
    /// or nil when nothing does (the existing connection is the way in).
    struct Question: Identifiable {
        let id = UUID()
        let code: String
        let message: String
        let confirm: String?
        let publicToken: String
        let metadata: JSONValue?
        let sessionId: String

        var title: String {
            switch code {
            case "link.duplicate": return "Already connected"
            case "link.overlap": return "Some of these are already connected"
            case "link.same_institution": return "Another login at this bank?"
            default: return "Already connected"
            }
        }

        var yes: String { confirm == "overlap" ? "Connect anyway" : "Yes, connect it" }
    }

    /// Fetching a token, or finishing after Link: the button spins.
    var busy = false
    var error: String?
    var question: Question?
    /// What just happened, for the screen's toast; the screen clears it.
    var done: String?
    private var session: PlaidLinkSession?
    private var pending: LinkToken?

    func connect(kind: String, model: AppModel) async {
        await start(model: model) { try await APIClient.shared.linkToken(kind: kind) }
    }

    func relink(item: Item, model: AppModel) async {
        await start(model: model) { try await APIClient.shared.relinkToken(itemId: item.id) }
    }

    private func start(model: AppModel, _ token: () async throws -> LinkToken) async {
        busy = true
        error = nil
        defer { busy = false }
        do {
            let t = try await token()
            pending = t
            let config = LinkTokenConfiguration(
                token: t.link_token,
                onSuccess: { [weak self] success in
                    Task { @MainActor in await self?.succeeded(success, model: model) }
                },
                onExit: { [weak self] exit in
                    Task { @MainActor in self?.exited(exit) }
                },
                onEvent: nil, onLoad: nil)
            let s = try Plaid.createPlaidLinkSession(configuration: config)
            session = s
            s.open(using: .viewController(Self.topViewController()))
        } catch let e as APIError {
            model.handle(e)
            error = e.errorDescription
        } catch {
            self.error = "Couldn't open the bank's window. \(error.localizedDescription)"
        }
    }

    private func succeeded(_ success: LinkSuccess, model: AppModel) async {
        session = nil
        guard let t = pending else { return }
        pending = nil
        busy = true
        defer { busy = false }
        do {
            if t.mode == "update" {
                let item = try await APIClient.shared.linkUpdateComplete(sessionId: t.link_session_id)
                done = "\(item.name) updated; sync queued"
                model.changed()
            } else {
                let metadata = success.metadata.metadataJSON.flatMap { try? JSON.decoder.decode(JSONValue.self, from: Data($0.utf8)) }
                try await exchange(publicToken: success.publicToken, metadata: metadata, sessionId: t.link_session_id, confirm: nil, model: model)
            }
        } catch let e as APIError {
            model.handle(e)
            error = e.errorDescription
        } catch {
            self.error = error.localizedDescription
        }
    }

    /// The exchange, or the guard's question. A public token lasts 30 minutes.
    private func exchange(publicToken: String, metadata: JSONValue?, sessionId: String, confirm: String?, model: AppModel) async throws {
        do {
            let item = try await APIClient.shared.linkExchange(publicToken: publicToken, metadata: metadata, sessionId: sessionId, confirm: confirm)
            done = "Connected \(item.name); first sync queued"
            model.changed()
        } catch APIError.linkGuard(let code, let message, _, _, let allowed) {
            question = Question(code: code, message: message, confirm: allowed, publicToken: publicToken, metadata: metadata, sessionId: sessionId)
        }
    }

    /// Yes to the guard's question: exchange with the answer it named.
    func answer(_ q: Question, model: AppModel) async {
        question = nil
        guard let confirm = q.confirm else { return }
        busy = true
        defer { busy = false }
        do {
            try await exchange(publicToken: q.publicToken, metadata: q.metadata, sessionId: q.sessionId, confirm: confirm, model: model)
        } catch let e as APIError {
            model.handle(e)
            error = e.errorDescription
        } catch {
            self.error = error.localizedDescription
        }
    }

    private func exited(_ exit: LinkExit) {
        session = nil
        pending = nil
        if let e = exit.error {
            error = e.displayMessage ?? e.errorMessage
        }
    }

    /// Where Link presents: whatever is on top of the key window.
    static func topViewController() -> UIViewController {
        let scenes = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }
        let windows = scenes.flatMap(\.windows)
        guard var vc = (windows.first { $0.isKeyWindow } ?? windows.first)?.rootViewController else {
            preconditionFailure("Link opened with no window")
        }
        while let next = vc.presentedViewController { vc = next }
        return vc
    }
}

/// The guard's question, the error, and the outcome, attached to a Link button.
private struct LinkFlowDialogs: ViewModifier {
    @SwiftUI.Environment(AppModel.self) private var model
    let flow: LinkFlow
    let onDone: (String) -> Void

    func body(content: Content) -> some View {
        content
            .alert(flow.question?.title ?? "", isPresented: Binding(get: { flow.question != nil }, set: { if !$0 { flow.question = nil } }),
                   presenting: flow.question) { q in
                if let _ = q.confirm {
                    Button(q.yes, role: q.confirm == "overlap" ? .destructive : nil) { Task { await flow.answer(q, model: model) } }
                }
                Button("Cancel", role: .cancel) { flow.question = nil }
            } message: { q in
                Text(q.message)
            }
            .alert("Couldn't connect", isPresented: Binding(get: { flow.error != nil }, set: { if !$0 { flow.error = nil } }),
                   presenting: flow.error) { _ in
                Button("OK", role: .cancel) { flow.error = nil }
            } message: { e in
                Text(e)
            }
            .onChange(of: flow.done) { _, d in
                if let d {
                    flow.done = nil
                    onDone(d)
                }
            }
    }
}

/// "Connect a bank": asks what kind (the product plan, docs/30 "Products"), then Link.
struct ConnectBankButton: View {
    @SwiftUI.Environment(AppModel.self) private var model
    @State private var flow = LinkFlow()
    @State private var choosing = false
    let onLinked: (String) -> Void

    var body: some View {
        Button {
            choosing = true
        } label: {
            HStack(spacing: 8) {
                if flow.busy { ProgressView().tint(JF.accentInk) }
                Text("Connect a bank")
            }
        }
        .buttonStyle(PrimaryButtonStyle())
        .disabled(flow.busy)
        .confirmationDialog("What are you connecting?", isPresented: $choosing, titleVisibility: .visible) {
            Button("Bank, card or loan") { Task { await flow.connect(kind: "banking", model: model) } }
            Button("Investment or retirement") { Task { await flow.connect(kind: "investments", model: model) } }
        } message: {
            Text("Checking, savings, credit cards, mortgages and loans (brokerage accounts at the same bank come along if you select them); or brokerage, 401(k), IRA and 529 accounts.")
        }
        .modifier(LinkFlowDialogs(flow: flow, onDone: onLinked))
    }
}

/// "Re-link" (a broken login, expiring consent) or "Add accounts" (a healthy
/// connection): Link in update mode. Same connection, nothing new billed.
struct RelinkButton: View {
    @SwiftUI.Environment(AppModel.self) private var model
    @State private var flow = LinkFlow()
    let item: Item
    let onDone: (String) -> Void

    var body: some View {
        Button {
            Task { await flow.relink(item: item, model: model) }
        } label: {
            HStack(spacing: 6) {
                if flow.busy { ProgressView() }
                Text(item.needsRelink ? "Re-link" : "Add accounts")
            }
        }
        .buttonStyle(SmallButtonStyle(primary: item.needsRelink || item.new_accounts_at != nil))
        .disabled(flow.busy)
        .modifier(LinkFlowDialogs(flow: flow, onDone: onDone))
    }
}
