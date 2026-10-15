import JFinancesKit
import SwiftUI

@main
struct JFinancesApp: App {
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

struct RootView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.scenePhase) private var scenePhase
    @State private var splash = true

    var body: some View {
        ZStack {
            JF.page.ignoresSafeArea()
            if model.isLinked {
                MainTabs()
            } else {
                LinkScreen()
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
        .task { await model.refreshGlance() }
        .onChange(of: scenePhase) { _, phase in
            if phase == .active { Task { await model.refreshGlance() } }
        }
        .onOpenURL { model.open($0) }
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
                NavigationStack { ActivityScreen() }
            }
            Tab("Insights", systemImage: "chart.bar.xaxis", value: AppTab.insights) {
                NavigationStack { InsightsScreen() }
            }
            Tab("Settings", systemImage: "gearshape", value: AppTab.settings) {
                SettingsTab()
            }
        }
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
