import Foundation
import Security

/// What linking leaves on the phone: the token, which server issued it, and
/// who it belongs to.
public struct Credential: Codable, Sendable, Equatable {
    public var token: String
    public var server: Server
    public var email: String
    public var displayName: String?
    public var linkedAt: Date

    public init(token: String, server: Server, email: String, displayName: String?, linkedAt: Date = Date()) {
        self.token = token
        self.server = server
        self.email = email
        self.displayName = displayName
        self.linkedAt = linkedAt
    }
}

/// The credential, in the Keychain, shared with the widget extension.
///
/// ⚠ `AfterFirstUnlockThisDeviceOnly`: a widget refreshes on a locked phone,
/// which is exactly when it is looked at. `ThisDeviceOnly` keeps the token out
/// of backups; a restored phone links again, which is right for a credential.
public enum Keychain {
    private static let account = "phone-credential"

    public static func read() -> Credential? {
        var out: AnyObject?
        var status = SecItemCopyMatching(query(group: true, returning: true) as CFDictionary, &out)
        if status == errSecMissingEntitlement || status == errSecItemNotFound {
            // A simulator build without the entitlement keeps it ungrouped.
            status = SecItemCopyMatching(query(group: false, returning: true) as CFDictionary, &out)
        }
        guard status == errSecSuccess, let data = out as? Data else { return nil }
        return try? JSONDecoder().decode(Credential.self, from: data)
    }

    @discardableResult
    public static func write(_ credential: Credential) -> Bool {
        delete()
        guard let data = try? JSONEncoder().encode(credential) else { return false }
        var add = query(group: true, returning: false)
        add[kSecValueData as String] = data
        add[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        var status = SecItemAdd(add as CFDictionary, nil)
        if status == errSecMissingEntitlement {
            add = query(group: false, returning: false)
            add[kSecValueData as String] = data
            add[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
            status = SecItemAdd(add as CFDictionary, nil)
        }
        return status == errSecSuccess
    }

    public static func delete() {
        SecItemDelete(query(group: true, returning: false) as CFDictionary)
        SecItemDelete(query(group: false, returning: false) as CFDictionary)
    }

    private static func query(group: Bool, returning: Bool) -> [String: Any] {
        var q: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: AppConfig.keychainService,
            kSecAttrAccount as String: account,
        ]
        if group { q[kSecAttrAccessGroup as String] = AppConfig.keychainGroup }
        if returning {
            q[kSecReturnData as String] = true
            q[kSecMatchLimit as String] = kSecMatchLimitOne
        }
        return q
    }
}
