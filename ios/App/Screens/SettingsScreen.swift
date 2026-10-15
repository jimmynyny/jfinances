import JFinancesKit
import SwiftUI

struct SettingsScreen: View {
    @Environment(AppModel.self) private var model
    @Environment(\.openURL) private var openURL
    @State private var confirmUnlink = false

    var body: some View {
        @Bindable var model = model
        Screen("Settings") {
            if let cred = model.credential {
                Panel("signed in") {
                    VStack(spacing: 0) {
                        KeyValueRow("person") { Text(model.me?.display_name ?? cred.displayName ?? cred.email) }
                        KeyValueRow("email") { Text(cred.email).font(JFFont.mono(13)) }
                        KeyValueRow("server") {
                            HStack(spacing: 6) {
                                if cred.server == .sandbox { Badge("sandbox", tone: .warn) }
                                Text(cred.server.api.host ?? "").font(JFFont.mono(12))
                            }
                        }
                        KeyValueRow("linked") { Text(cred.linkedAt.formatted(date: .abbreviated, time: .shortened)).font(JFFont.mono(13)) }
                    }
                }
                Panel("banks", flush: true) {
                    NavigationLink(value: SettingsRoute.connections) {
                        HStack {
                            VStack(alignment: .leading, spacing: 3) {
                                Text("Connections").font(JFFont.sans(15, .medium)).foregroundStyle(JF.ink)
                                Fine("Connect, re-link, sync or unlink a bank; add an offline account.")
                            }
                            Spacer()
                            Image(systemName: "chevron.right").font(.system(size: 11, weight: .semibold)).foregroundStyle(JF.ink3)
                        }
                        .padding(.horizontal, 16)
                        .padding(.vertical, 12)
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                }
                Panel("privacy") {
                    VStack(alignment: .leading, spacing: 10) {
                        if Biometrics.available {
                            Toggle(isOn: Binding(get: { model.lockEnabled }, set: { on in Task { _ = await model.setLock(on) } })) {
                                VStack(alignment: .leading, spacing: 2) {
                                    Text("Lock with \(Biometrics.kind)").font(JFFont.sans(15, .medium)).foregroundStyle(JF.ink)
                                    Fine("Asked for each time the app opens or comes back.")
                                }
                            }
                            .tint(JF.accent)
                        } else {
                            VStack(alignment: .leading, spacing: 2) {
                                Text("Lock with Face ID").font(JFFont.sans(15, .medium)).foregroundStyle(JF.ink3)
                                Fine("Set a passcode on this phone first, in the iPhone's Settings.")
                            }
                        }
                        Rule()
                        Toggle(isOn: $model.blur) {
                            VStack(alignment: .leading, spacing: 2) {
                                Text("Blur numbers").font(JFFont.sans(15, .medium)).foregroundStyle(JF.ink)
                                Fine("For screenshots: every figure in the app blurs.")
                            }
                        }
                        .tint(JF.accent)
                        Rule()
                        Text("This phone does what the dashboard does: it reads everything and edits what you tell it to. It never moves money and never talks to a bank itself; connecting one goes through the same secure window as on the web.")
                            .font(JFFont.sans(13)).foregroundStyle(JF.ink2)
                    }
                }
                Panel("widgets") {
                    Text("Touch and hold the Home Screen or the Lock Screen, tap Edit, then Add Widget, and pick jFinances: net worth, this month, coming up, or one account.")
                        .font(JFFont.sans(13)).foregroundStyle(JF.ink2)
                }
                Button("Open the dashboard") { openURL(cred.server.dashboard) }
                    .buttonStyle(QuietButtonStyle())
                Button("Unlink this phone") { confirmUnlink = true }
                    .buttonStyle(QuietButtonStyle(destructive: true))
                    .confirmationDialog("Unlink this phone?", isPresented: $confirmUnlink, titleVisibility: .visible) {
                        Button("Unlink", role: .destructive) { Task { await model.unlink() } }
                    } message: {
                        Text("Its token is revoked and the widgets go blank. Sign in again any time.")
                    }
            }
            Fine("jFinances \(Self.version)").frame(maxWidth: .infinity).padding(.top, 8)
        }
        .navigationDestination(for: SettingsRoute.self) { route in
            switch route {
            case .connections: ConnectionsScreen()
            }
        }
    }

    static var version: String {
        let v = Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "?"
        let b = Bundle.main.object(forInfoDictionaryKey: "CFBundleVersion") as? String ?? "?"
        return "\(v) (\(b))"
    }
}

enum SettingsRoute: Hashable {
    case connections
}

/// The Settings tab owns its path so the Overview's "needs re-linking" note
/// (and `jfinances://settings/connections`) can open Connections directly.
struct SettingsTab: View {
    @Environment(AppModel.self) private var model
    @State private var path: [SettingsRoute] = []

    var body: some View {
        NavigationStack(path: $path) { SettingsScreen() }
            .onChange(of: model.showConnections, initial: true) { _, wanted in
                if wanted {
                    model.showConnections = false
                    path = [.connections]
                }
            }
    }
}
