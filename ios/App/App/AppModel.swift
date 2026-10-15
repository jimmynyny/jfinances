import Foundation
import JFinancesKit
import Observation
import SwiftUI
import WidgetKit

enum AppTab: Hashable { case overview, accounts, activity, insights, settings }

enum InsightsSection: String, CaseIterable, Identifiable, Hashable {
    case cashflow, spending, subscriptions, networth, investing
    var id: String { rawValue }
    var title: String {
        switch self {
        case .cashflow: return "Cash flow"
        case .spending: return "Spending"
        case .subscriptions: return "Subscriptions"
        case .networth: return "Net worth & debt"
        case .investing: return "Investing"
        }
    }
}

/// The app's shared state: whether the phone is linked, to whom, the last
/// glance, and the blur switch. Screens read; only this type writes the
/// Keychain or the cache.
@MainActor
@Observable
final class AppModel {
    var credential: Credential?
    var me: Me?
    var glance: Glance?
    var glanceFetchedAt: Date?
    var lastError: String?
    var tab: AppTab = .overview
    var insightsSection: InsightsSection = .cashflow
    /// An account a deep link asked for; the Accounts tab pushes it and clears it.
    var pendingAccountId: String?
    /// Settings → Connections is wanted (a bank needs re-linking); Settings pushes it.
    var showConnections = false
    /// Bumped by pull-to-refresh; every loader on screen reloads.
    var refreshToken = UUID()
    var blur: Bool {
        didSet { UserDefaults.standard.set(blur, forKey: "jf.blur") }
    }

    var isLinked: Bool { credential != nil }

    init() {
        #if DEBUG
        // Simulator QA against a local server: `SIMCTL_CHILD_JF_DEBUG_TOKEN=…`
        // stands in for the Access sign-in a simulator cannot complete.
        if let token = ProcessInfo.processInfo.environment["JF_DEBUG_TOKEN"], !token.isEmpty {
            Keychain.write(Credential(token: token, server: .local, email: "simulator@local", displayName: "Simulator"))
        }
        #endif
        credential = Keychain.read()
        blur = UserDefaults.standard.bool(forKey: "jf.blur")
        if let cached = GlanceCache.load() {
            glance = cached.glance
            glanceFetchedAt = cached.fetchedAt
        }
    }

    // MARK: - reads

    /// The glance (net worth, this month, coming up). Cheap: widgets share it.
    func refreshGlance(force: Bool = false) async {
        guard isLinked else { return }
        let (cached, error) = await GlanceCache.fetch(maxAge: force ? 0 : 60)
        if let cached {
            glance = cached.glance
            glanceFetchedAt = cached.fetchedAt
        }
        if let error { handle(error) } else { lastError = nil }
        if me == nil, isLinked { me = try? await APIClient.shared.me() }
        WidgetCenter.shared.reloadAllTimelines()
    }

    func pullToRefresh() async {
        refreshToken = UUID()
        await refreshGlance(force: true)
    }

    /// Something was edited on this phone: every loader reloads, the glance and
    /// the widgets with it.
    func changed() {
        refreshToken = UUID()
        Task { await refreshGlance(force: true) }
    }

    func openConnections() {
        tab = .settings
        showConnections = true
    }

    /// Every screen funnels API errors here, so a dead token is handled once:
    /// forget it and go back to sign-in.
    func handle(_ error: APIError) {
        if error.tokenIsDead { signOutLocally() }
        lastError = error.errorDescription
    }

    // MARK: - the link

    func completeLink(_ r: RedeemResponse, server: Server) {
        let cred = Credential(token: r.token, server: server, email: r.email, displayName: r.display_name)
        Keychain.write(cred)
        GlanceCache.clear()
        credential = cred
        me = nil
        glance = nil
        lastError = nil
        tab = .overview
        Task { await refreshGlance(force: true) }
    }

    func unlink() async {
        // Whatever the server says, the token leaves this phone.
        try? await APIClient.shared.unlink()
        signOutLocally()
    }

    func signOutLocally() {
        Keychain.delete()
        GlanceCache.clear()
        credential = nil
        me = nil
        glance = nil
        glanceFetchedAt = nil
        WidgetCenter.shared.reloadAllTimelines()
    }

    // MARK: - deep links

    /// `jfinances://overview`, `://accounts`, `://account/<id>`, `://activity`,
    /// `://insights/<section>`. The sign-in callback (`://linked?…`) is
    /// consumed by the web-auth session and ignored here.
    func open(_ url: URL) {
        guard url.scheme == AppConfig.scheme else { return }
        let parts = url.pathComponents.filter { $0 != "/" }
        switch url.host {
        case "overview": tab = .overview
        case "accounts": tab = .accounts
        case "account":
            if let id = parts.first, !id.isEmpty {
                pendingAccountId = id
                tab = .accounts
            }
        case "activity": tab = .activity
        case "insights":
            if let s = parts.first.flatMap(InsightsSection.init(rawValue:)) { insightsSection = s }
            tab = .insights
        case "settings":
            if parts.first == "connections" { showConnections = true }
            tab = .settings
        default: break
        }
    }
}
