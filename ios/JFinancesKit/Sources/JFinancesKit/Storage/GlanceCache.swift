import Foundation

/// The last glance, on disk, so a widget drawn while offline shows the last
/// known figures with their age rather than an empty box, and so several
/// widgets refreshing together share one request.
///
/// Each process keeps its own copy (the app's and the extension's containers
/// are separate); the token is what they share, through the Keychain.
public struct CachedGlance: Codable, Sendable {
    public var glance: Glance
    public var fetchedAt: Date
    /// Which server it came from: a phone relinked elsewhere must not show
    /// the other environment's numbers.
    public var server: Server

    public init(glance: Glance, fetchedAt: Date = Date(), server: Server) {
        self.glance = glance
        self.fetchedAt = fetchedAt
        self.server = server
    }
}

public enum GlanceCache {
    private static var url: URL {
        FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask)[0].appendingPathComponent("glance.json")
    }

    public static func load() -> CachedGlance? {
        guard let data = try? Data(contentsOf: url),
              let cached = try? JSONDecoder().decode(CachedGlance.self, from: data) else { return nil }
        // A different (or no) credential: the cache belongs to someone else.
        guard let cred = Keychain.read(), cred.server == cached.server else { return nil }
        return cached
    }

    public static func save(_ cached: CachedGlance) {
        guard let data = try? JSONEncoder().encode(cached) else { return }
        try? data.write(to: url, options: [.atomic, .completeFileProtectionUntilFirstUserAuthentication])
    }

    public static func clear() {
        try? FileManager.default.removeItem(at: url)
    }

    /// The cached glance when it is younger than `maxAge`, else a fresh one
    /// (saved). Falls back to the cache, however old, when the fetch fails;
    /// the error is returned beside it so the caller can say "as of".
    public static func fetch(maxAge: TimeInterval) async -> (CachedGlance?, APIError?) {
        let cached = load()
        if let cached, Date().timeIntervalSince(cached.fetchedAt) < maxAge { return (cached, nil) }
        do {
            guard let cred = Keychain.read() else { return (nil, .notLinked) }
            let fresh = CachedGlance(glance: try await APIClient.shared.glance(), server: cred.server)
            save(fresh)
            return (fresh, nil)
        } catch let e as APIError {
            if e.tokenIsDead { clear() }
            return (e.tokenIsDead ? nil : cached, e)
        } catch {
            return (cached, .transport(error.localizedDescription))
        }
    }
}
