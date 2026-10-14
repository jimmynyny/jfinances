import AuthenticationServices
import JFinancesKit
import UIKit

enum LinkError: LocalizedError {
    case cancelled, couldNotStart, badCallback

    var errorDescription: String? {
        switch self {
        case .cancelled: return "Sign-in was cancelled."
        case .couldNotStart: return "Couldn't open the sign-in window."
        case .badCallback: return "Sign-in came back without a valid code. Try again."
        }
    }
}

/// Linking, end to end (docs/40 §5): open the dashboard's link endpoint in a
/// system web sheet, where Cloudflare Access does the login; catch the bounce
/// to `jfinances://linked?code=…&nonce=…`; check the nonce; trade the code
/// for this phone's token on the API hostname.
@MainActor
final class LinkService: NSObject, ASWebAuthenticationPresentationContextProviding {
    static let shared = LinkService()
    private var session: ASWebAuthenticationSession?

    func link(server: Server) async throws -> RedeemResponse {
        let nonce = Self.makeNonce()
        var comps = URLComponents(url: server.dashboard.appendingPathComponent("/api/v1/mobile/link"),
                                  resolvingAgainstBaseURL: false)!
        comps.queryItems = [URLQueryItem(name: "nonce", value: nonce), URLQueryItem(name: "name", value: Self.deviceName)]
        let url = comps.url!

        let callback: URL = try await withCheckedThrowingContinuation { cont in
            var resumed = false
            let s = ASWebAuthenticationSession(url: url, callback: .customScheme(AppConfig.scheme)) { url, error in
                guard !resumed else { return }
                resumed = true
                if let url {
                    cont.resume(returning: url)
                } else if let e = error as? ASWebAuthenticationSessionError, e.code == .canceledLogin {
                    cont.resume(throwing: LinkError.cancelled)
                } else {
                    cont.resume(throwing: error ?? LinkError.badCallback)
                }
            }
            // Not ephemeral: an Access session already open in Safari makes
            // linking one tap instead of an emailed code.
            s.prefersEphemeralWebBrowserSession = false
            s.presentationContextProvider = self
            session = s
            if !s.start(), !resumed {
                resumed = true
                cont.resume(throwing: LinkError.couldNotStart)
            }
        }
        session = nil

        guard let items = URLComponents(url: callback, resolvingAgainstBaseURL: false)?.queryItems,
              let code = items.first(where: { $0.name == "code" })?.value, !code.isEmpty,
              let back = items.first(where: { $0.name == "nonce" })?.value, back == nonce
        else { throw LinkError.badCallback }
        return try await APIClient.shared.redeem(server: server, code: code, nonce: nonce, name: Self.deviceName)
    }

    nonisolated func presentationAnchor(for session: ASWebAuthenticationSession) -> ASPresentationAnchor {
        MainActor.assumeIsolated {
            let scenes = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }
            let windows = scenes.flatMap(\.windows)
            if let key = windows.first(where: \.isKeyWindow) ?? windows.first { return key }
            guard let scene = scenes.first else { preconditionFailure("sign-in presented with no window scene") }
            return UIWindow(windowScene: scene)
        }
    }

    /// 32 URL-safe characters, as the server's `[A-Za-z0-9_-]{8,64}` wants.
    static func makeNonce() -> String {
        let alphabet = Array("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")
        var rng = SystemRandomNumberGenerator()
        return String((0..<32).map { _ in alphabet[Int.random(in: 0..<alphabet.count, using: &rng)] })
    }

    /// What Settings → phones on the dashboard calls this phone.
    static var deviceName: String {
        "\(UIDevice.current.model) · iOS \(UIDevice.current.systemVersion)"
    }
}
