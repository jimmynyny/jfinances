import CoreText
import SwiftUI
import UIKit

/// The design system's tokens (packages/ui/src/styles/tokens.css), light and
/// dark. Square corners, 1px rules, one signal accent, mono for labels and
/// figures. Money colours are never the accent.
public enum JF {
    public static let page = Color(light: 0xF3F3EF, dark: 0x0F1012)
    public static let panel = Color(light: 0xFFFFFF, dark: 0x161719)
    public static let panel2 = Color(light: 0xF8F8F5, dark: 0x1D1E21)
    public static let ink = Color(light: 0x17191C, dark: 0xF7F7F3)
    public static let ink2 = Color(light: 0x4E5259, dark: 0xD2D5DA)
    public static let ink3 = Color(light: 0x666B73, dark: 0xA3A7AE)
    public static let line = Color(light: 0xD8D8D1, dark: 0x2A2C30)
    public static let lineStrong = Color(light: 0x17191C, dark: 0xF1F1EC)
    public static let grid = Color(light: 0xE6E6E0, dark: 0x232529)
    public static let accent = Color(light: 0xE4531B, dark: 0xFF6A34)
    public static let accentInk = Color(light: 0xFFFFFF, dark: 0x17191C)
    public static let accentWash = Color(light: 0xFBE9E0, dark: 0x33211A)
    public static let accentText = Color(light: 0xB8400F, dark: 0xFF6A34)
    public static let pos = Color(light: 0x1B7A3D, dark: 0x4CD07A)
    public static let posWash = Color(light: 0xE3F3E8, dark: 0x16281C)
    public static let neg = Color(light: 0xB32318, dark: 0xFF7D72)
    public static let negWash = Color(light: 0xFBE5E3, dark: 0x2E1816)
    public static let warn = Color(light: 0xE3A008, dark: 0xE3A008)
    public static let good = Color(light: 0x0CA30C, dark: 0x0CA30C)
    public static let critical = Color(light: 0xD03B3B, dark: 0xD03B3B)
    public static let pixelOff = Color(light: 0xE9E8E2, dark: 0x25272B)
    public static let divPos = Color(light: 0x2A78D6, dark: 0x3987E5)
    public static let divNeg = Color(light: 0xB32318, dark: 0xE34948)
    public static let reg = Color(light: 0xA3A7AD, dark: 0x4A4D53)
    public static let other = Color(light: 0xA3A7AD, dark: 0x5B5F66)
    /// Categorical series, fixed order: colour follows the entity, not its rank.
    public static let series: [Color] = [
        Color(light: 0x2A78D6, dark: 0x3987E5), Color(light: 0x1BAF7A, dark: 0x199E70),
        Color(light: 0xEDA100, dark: 0xC98500), Color(light: 0x4A3AA7, dark: 0x9085E9),
        Color(light: 0xE87BA4, dark: 0xD55181), Color(light: 0x008300, dark: 0x008300),
    ]

    public static func seriesColor(_ i: Int) -> Color { i >= 0 && i < series.count ? series[i] : other }

    public static let gutter: CGFloat = 16
}

public extension Color {
    init(light: UInt32, dark: UInt32) {
        self.init(uiColor: UIColor { traits in
            UIColor(hex: traits.userInterfaceStyle == .dark ? dark : light)
        })
    }
}

extension UIColor {
    convenience init(hex: UInt32) {
        self.init(red: CGFloat((hex >> 16) & 0xFF) / 255, green: CGFloat((hex >> 8) & 0xFF) / 255,
                  blue: CGFloat(hex & 0xFF) / 255, alpha: 1)
    }
}

/// IBM Plex Sans for the interface, Plex Mono for labels and figures, and the
/// dot-matrix face (Doto, square dots) for the one readout per screen.
public enum JFFont {
    public enum Weight { case regular, medium, semibold }

    public static func sans(_ size: CGFloat, _ weight: Weight = .regular, relativeTo style: Font.TextStyle = .body) -> Font {
        .custom(name("IBMPlexSans", weight), size: size, relativeTo: style)
    }

    public static func mono(_ size: CGFloat, _ weight: Weight = .regular, relativeTo style: Font.TextStyle = .body) -> Font {
        .custom(name("IBMPlexMono", weight), size: size, relativeTo: style)
    }

    /// The readout face. Fixed size: it is drawn to fit its box, not reflowed.
    public static func pixel(_ size: CGFloat) -> Font { .custom("JFDotoPixel", fixedSize: size) }

    public static func uiSans(_ size: CGFloat, _ weight: Weight = .regular) -> UIFont {
        UIFont(name: name("IBMPlexSans", weight), size: size) ?? .systemFont(ofSize: size)
    }

    public static func uiMono(_ size: CGFloat, _ weight: Weight = .regular) -> UIFont {
        UIFont(name: name("IBMPlexMono", weight), size: size) ?? .monospacedSystemFont(ofSize: size, weight: .regular)
    }

    private static func name(_ family: String, _ weight: Weight) -> String {
        switch weight {
        case .regular: return "\(family)-Regular"
        case .medium: return "\(family)-Medium"
        case .semibold: return "\(family)-SemiBold"
        }
    }

    /// `UIAppFonts` registers the faces at launch; this is the belt to those
    /// braces for a process that did not (an extension, a preview). Calling it
    /// twice is harmless.
    public static func register(in bundle: Bundle = .main) {
        for url in bundle.urls(forResourcesWithExtension: "ttf", subdirectory: nil) ?? [] {
            CTFontManagerRegisterFontsForURL(url as CFURL, .process, nil)
        }
    }
}
