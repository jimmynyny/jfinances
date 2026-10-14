// swift-tools-version: 5.9
import PackageDescription

// Shared by the app and the widget extension: the API client, the JSON
// shapes, the Keychain, and the design system's pieces both of them draw.
let package = Package(
    name: "JFinancesKit",
    platforms: [.iOS("26.0")],
    products: [
        .library(name: "JFinancesKit", targets: ["JFinancesKit"]),
    ],
    targets: [
        .target(name: "JFinancesKit", path: "Sources/JFinancesKit"),
    ]
)
