import LocalAuthentication

/// The phone's own lock, for the app: Face ID or Touch ID, with the passcode
/// as the fallback iOS offers. The token stays in the Keychain either way;
/// this only keeps the screens from showing until the owner is there.
enum Biometrics {
    /// Whether the phone can ask at all (a passcode is set; Face ID, Touch ID
    /// or the passcode will do).
    static var available: Bool {
        LAContext().canEvaluatePolicy(.deviceOwnerAuthentication, error: nil)
    }

    /// "Face ID", "Touch ID" or "passcode": how the switch and the prompt name it.
    static var kind: String {
        let ctx = LAContext()
        guard ctx.canEvaluatePolicy(.deviceOwnerAuthenticationWithBiometrics, error: nil) else { return "passcode" }
        switch ctx.biometryType {
        case .faceID: return "Face ID"
        case .touchID: return "Touch ID"
        case .opticID: return "Optic ID"
        default: return "passcode"
        }
    }

    /// Asks. False when cancelled, failed, or not available.
    static func authenticate(reason: String) async -> Bool {
        let ctx = LAContext()
        ctx.localizedCancelTitle = "Cancel"
        guard ctx.canEvaluatePolicy(.deviceOwnerAuthentication, error: nil) else { return false }
        return (try? await ctx.evaluatePolicy(.deviceOwnerAuthentication, localizedReason: reason)) ?? false
    }
}
