import SwiftUI

/// The "blur" switch (the web's top-right toggle): every figure blurs so a
/// screenshot can be shared. The radius scales with the text, as on the web,
/// so a 60 pt readout is as unreadable as a 12 pt caption.
public struct BlurNumbersKey: EnvironmentKey {
    public static let defaultValue = false
}

public extension EnvironmentValues {
    var blurNumbers: Bool {
        get { self[BlurNumbersKey.self] }
        set { self[BlurNumbersKey.self] = newValue }
    }
}

public struct FigureBlur: ViewModifier {
    @Environment(\.blurNumbers) private var blur
    let size: CGFloat

    public func body(content: Content) -> some View {
        content
            .blur(radius: blur ? max(5, size * 0.42) : 0)
            .accessibilityHidden(blur)
            .animation(.easeOut(duration: 0.14), value: blur)
    }
}

public extension View {
    /// Mark a view as a figure: it blurs when the switch is on.
    func figure(size: CGFloat = 14) -> some View { modifier(FigureBlur(size: size)) }
}
