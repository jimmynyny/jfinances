// jfinances for Android (docs/86-android.md). One module: the app, its
// widgets and the kit they share, as ios/ is the app, its widget extension and
// JFinancesKit.
pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
    }
}

rootProject.name = "jfinances"
include(":app")
