// AGP compiles Kotlin itself (built-in Kotlin, AGP 9); naming the Kotlin
// plugin here only pins the compiler version the Compose and serialization
// plugins must match.
plugins {
    alias(libs.plugins.android.application) apply false
    alias(libs.plugins.kotlin.android) apply false
    alias(libs.plugins.kotlin.compose) apply false
    alias(libs.plugins.kotlin.serialization) apply false
}
