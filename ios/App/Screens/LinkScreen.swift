import JFinancesKit
import SwiftUI

/// Not linked yet: sign in through Cloudflare Access once, and the phone gets
/// its own read-only token (docs/40 §5).
struct LinkScreen: View {
    @Environment(AppModel.self) private var model
    @State private var server = AppConfig.defaultServer
    @State private var working = false
    @State private var error: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Spacer(minLength: 40)
            LogoMark().frame(width: 96, height: 96)
            Text("jFinances")
                .font(JFFont.sans(34, .semibold))
                .foregroundStyle(JF.ink)
                .padding(.top, 28)
            Text("The household's money, on your phone and your Home Screen.")
                .font(JFFont.sans(17))
                .foregroundStyle(JF.ink2)
                .padding(.top, 6)
            Spacer(minLength: 32)

            VStack(alignment: .leading, spacing: 12) {
                Caption("server")
                Chips(options: Server.allCases.map { ($0, $0.label.lowercased()) }, value: $server)
                Button {
                    Task { await signIn() }
                } label: {
                    HStack(spacing: 8) {
                        if working { ProgressView().tint(JF.accentInk) }
                        Text(working ? "Signing in…" : "Sign in")
                    }
                }
                .buttonStyle(PrimaryButtonStyle())
                .disabled(working)
                .padding(.top, 8)
                if let error {
                    ErrorNote(error)
                }
                Text("You sign in with the same emailed code as the dashboard. This phone can read everything and change nothing; unlink it any time from Settings on either side.")
                    .font(JFFont.mono(11))
                    .foregroundStyle(JF.ink3)
                    .padding(.top, 4)
            }
            Spacer(minLength: 24)
        }
        .padding(.horizontal, 24)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .leading)
        .background(JF.page)
    }

    private func signIn() async {
        working = true
        error = nil
        defer { working = false }
        do {
            let r = try await LinkService.shared.link(server: server)
            model.completeLink(r, server: server)
        } catch LinkError.cancelled {
            return
        } catch {
            self.error = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
        }
    }
}

/// The app icon's motif, live: a pixel sparkline whose newest cell glows.
struct LogoMark: View {
    private let trace = [1, 2, 2, 4, 3, 5, 6, 6, 8]
    @State private var lit = 0

    var body: some View {
        Canvas { ctx, size in
            let n = 9
            let pitch = size.width / CGFloat(n)
            let cell = pitch * 0.82
            for c in 0..<n {
                for r in 0..<n {
                    let rect = CGRect(x: CGFloat(c) * pitch, y: CGFloat(n - 1 - r) * pitch, width: cell, height: cell)
                    let level = trace[c]
                    let color: Color
                    if c >= lit { color = JF.pixelOff }
                    else if r == level { color = c == n - 1 ? JF.accent : JF.ink }
                    else if r < level { color = JF.ink.opacity(level - r <= 2 ? 0.38 : 0.16) }
                    else { color = JF.pixelOff }
                    ctx.fill(Path(rect), with: .color(color))
                }
            }
        }
        .task {
            for i in 0...9 {
                lit = i
                try? await Task.sleep(for: .milliseconds(70))
            }
        }
        .accessibilityHidden(true)
    }
}
