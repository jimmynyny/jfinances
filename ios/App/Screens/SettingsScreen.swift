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
                Panel("privacy") {
                    VStack(alignment: .leading, spacing: 10) {
                        Toggle(isOn: $model.blur) {
                            VStack(alignment: .leading, spacing: 2) {
                                Text("Blur numbers").font(JFFont.sans(15, .medium)).foregroundStyle(JF.ink)
                                Fine("For screenshots: every figure in the app blurs.")
                            }
                        }
                        .tint(JF.accent)
                        Rule()
                        Text("This phone is read-only: it can see everything on the dashboard and change nothing. It never talks to a bank.")
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
    }

    static var version: String {
        let v = Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "?"
        let b = Bundle.main.object(forInfoDictionaryKey: "CFBundleVersion") as? String ?? "?"
        return "\(v) (\(b))"
    }
}
