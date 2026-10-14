import Foundation

/// Which jfinances the phone talks to. Each environment has a dashboard
/// hostname (behind Cloudflare Access: where linking starts) and an API
/// hostname (no Access: where the phone's own token is accepted). docs/40 §5.
public enum Server: String, CaseIterable, Codable, Sendable, Identifiable {
    case production, sandbox
    #if DEBUG
    /// A developer's own server, for the simulator only. Not in release builds.
    case local
    #endif

    public var id: String { rawValue }
    public var label: String {
        switch self {
        case .production: return "Production"
        case .sandbox: return "Sandbox"
        #if DEBUG
        case .local: return "Local"
        #endif
        }
    }

    public var dashboard: URL {
        switch self {
        case .production: return URL(string: "https://jfinances.sellingtcg.com")!
        case .sandbox: return URL(string: "https://jfinances-sandbox.sellingtcg.com")!
        #if DEBUG
        case .local: return URL(string: "http://127.0.0.1:8000")!
        #endif
        }
    }

    public var api: URL {
        switch self {
        case .production: return URL(string: "https://jfinances-api.sellingtcg.com")!
        case .sandbox: return URL(string: "https://jfinances-sandbox-api.sellingtcg.com")!
        #if DEBUG
        case .local: return URL(string: "http://127.0.0.1:8001")!
        #endif
        }
    }
}

public enum AppConfig {
    /// The server bounces the link to `jfinances://linked?code=…&nonce=…`;
    /// widgets open `jfinances://overview` and friends.
    public static let scheme = "jfinances"
    public static let keychainService = "com.daedalustcg.jfinances"
    /// Both targets claim this keychain access group
    /// (`$(AppIdentifierPrefix)com.daedalustcg.jfinances`), which is how the
    /// widget reads the token the app stored.
    public static let keychainGroup = "TH5WXDPTS8.com.daedalustcg.jfinances"

    /// Which server the sign-in screen offers first (Info.plist `JFDefaultServer`).
    public static var defaultServer: Server {
        (Bundle.main.object(forInfoDictionaryKey: "JFDefaultServer") as? String).flatMap(Server.init(rawValue:))
            ?? .production
    }
}
