import JFinancesKit
import SwiftUI

@main
struct JFinancesApp: App {
    @UIApplicationDelegateAdaptor private var delegate: AppDelegate
    @State private var model = AppModel()

    init() {
        JFFont.register()
        Appearance.apply()
    }

    var body: some Scene {
        WindowGroup {
            RootView()
                .environment(model)
                .environment(\.blurNumbers, model.blur)
                .tint(JF.accent)
        }
    }
}

/// Which ways the screen may turn: an iPad any way; the open iPhone Duo, which is
/// as wide as an iPad, either way up or on its side; a phone (and the Duo folded)
/// upright only, as before.
final class AppDelegate: NSObject, UIApplicationDelegate {
    func application(_ application: UIApplication, supportedInterfaceOrientationsFor window: UIWindow?) -> UIInterfaceOrientationMask {
        if UIDevice.current.userInterfaceIdiom == .pad { return .all }
        return window?.traitCollection.horizontalSizeClass == .regular ? .allButUpsideDown : .portrait
    }
}

struct RootView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.scenePhase) private var scenePhase
    @Environment(\.horizontalSizeClass) private var sizeClass
    @State private var splash = true

    var body: some View {
        @Bindable var model = model
        ZStack {
            JF.page.ignoresSafeArea()
            if model.isLinked {
                MainTabs()
            } else {
                LinkScreen()
            }
            if model.locked {
                // Over everything, the splash included: the figures stay hidden until Face ID.
                LockScreen().transition(.opacity).zIndex(2)
            } else if scenePhase != .active, model.lockEnabled {
                // Leaving: the app switcher's snapshot shows the cover, not the figures.
                SplashView().zIndex(2)
            }
            if splash {
                SplashView().transition(.opacity).zIndex(1)
            }
        }
        .task {
            try? await Task.sleep(for: .milliseconds(1100))
            withAnimation(.easeOut(duration: 0.35)) { splash = false }
        }
        .animation(.easeInOut(duration: 0.2), value: model.isLinked)
        .animation(.easeInOut(duration: 0.2), value: model.locked)
        .task { await model.refreshGlance() }
        .onChange(of: scenePhase) { _, phase in
            switch phase {
            case .background: model.background()
            case .active:
                Task { await model.refreshGlance() }
                if model.locked { Task { await model.unlock() } }
            default: break
            }
        }
        .onOpenURL { model.open($0) }
        .onChange(of: sizeClass) {
            // The Duo folded or unfolded: ask again which ways it may turn (folded on
            // its side, it turns back upright).
            for case let scene as UIWindowScene in UIApplication.shared.connectedScenes {
                scene.keyWindow?.rootViewController?.setNeedsUpdateOfSupportedInterfaceOrientations()
            }
        }
        .alert("Lock jFinances with \(Biometrics.kind)?", isPresented: $model.offerLock) {
            Button("Use \(Biometrics.kind)") { model.lockEnabled = true }
            Button("Not now", role: .cancel) {}
        } message: {
            Text("The app asks for it each time it opens, so a phone left on the table doesn't show the household's money. You can change this in Settings.")
        }
    }
}

/// The cover while the app waits for Face ID: the mark, the name, and a way to ask again.
struct LockScreen: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        ZStack {
            JF.page.ignoresSafeArea()
            VStack(spacing: 18) {
                Image("LaunchIcon")
                Text("jFinances").font(JFFont.sans(30, .semibold)).foregroundStyle(JF.ink)
                Button {
                    Task { await model.unlock() }
                } label: {
                    HStack(spacing: 8) {
                        Image(systemName: Biometrics.kind == "Face ID" ? "faceid" : Biometrics.kind == "Touch ID" ? "touchid" : "lock")
                        Text("Unlock")
                    }
                }
                .buttonStyle(PrimaryButtonStyle())
                .padding(.horizontal, 48)
                .padding(.top, 12)
                .disabled(model.unlocking)
            }
        }
        .task { await model.unlock() }
        .accessibilityLabel("Locked")
    }
}

struct MainTabs: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        @Bindable var model = model
        TabView(selection: $model.tab) {
            Tab("Overview", systemImage: "square.grid.2x2", value: AppTab.overview) {
                NavigationStack { OverviewScreen() }
            }
            Tab("Accounts", systemImage: "building.columns", value: AppTab.accounts) {
                AccountsTab()
            }
            Tab("Activity", systemImage: "list.bullet.rectangle", value: AppTab.activity) {
                ActivityTab()
            }
            Tab("Insights", systemImage: "chart.bar.xaxis", value: AppTab.insights) {
                NavigationStack { InsightsScreen() }
            }
            Tab("Settings", systemImage: "gearshape", value: AppTab.settings) {
                SettingsTab()
            }
        }
        // A phone keeps the tab bar; an iPad gets the tab bar on top, or a sidebar.
        .tabViewStyle(.sidebarAdaptable)
    }
}

/// Navigation bar type in Plex, as the dashboard's page headers.
enum Appearance {
    static func apply() {
        let nav = UINavigationBar.appearance()
        nav.largeTitleTextAttributes = [.font: JFFont.uiSans(30, .semibold)]
        nav.titleTextAttributes = [.font: JFFont.uiSans(17, .semibold)]
        UISegmentedControl.appearance().setTitleTextAttributes([.font: JFFont.uiMono(12, .medium)], for: .normal)
    }
}

/// The first thing on screen: the launch screen's icon with the name under it,
/// for a moment while the first glance loads behind it.
struct SplashView: View {
    var body: some View {
        ZStack {
            JF.page.ignoresSafeArea()
            // Centred where the launch screen draws it, so the hand-off doesn't move it.
            Image("LaunchIcon")
                .overlay(alignment: .bottom) {
                    Text("jFinances")
                        .font(JFFont.sans(30, .semibold))
                        .foregroundStyle(JF.ink)
                        .fixedSize()
                        .offset(y: 58)
                }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("jFinances")
    }
}
