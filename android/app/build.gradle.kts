import java.util.Properties
import org.jetbrains.kotlin.gradle.dsl.JvmTarget

plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.kotlin.serialization)
}

// The build number must climb or the phone keeps the old app. Scripts pass
// minutes since 2026-01-01 (as the iOS build does); a plain build is 1.
val buildNumber = providers.gradleProperty("jfBuild").orNull?.toInt() ?: 1

// Release signing lives outside the repository (Scripts/deploy-apk.sh makes
// it): a properties file naming the keystore and its passwords.
val signingFile = providers.gradleProperty("jfSigning").orNull?.let { file(it) }?.takeIf { it.exists() }

android {
    namespace = "com.daedalustcg.jfinances"
    compileSdk = 37

    defaultConfig {
        applicationId = "com.daedalustcg.jfinances"
        minSdk = 31
        targetSdk = 36
        versionCode = buildNumber
        versionName = "0.1.0"
        // Which server the sign-in screen offers first.
        buildConfigField("String", "DEFAULT_SERVER", "\"production\"")
        // A developer's own server (and the emulator's token shortcut): debug builds only.
        buildConfigField("boolean", "LOCAL_SERVER", "false")
    }

    signingConfigs {
        if (signingFile != null) {
            create("release") {
                val p = Properties().apply { signingFile.inputStream().use { load(it) } }
                storeFile = file(p.getProperty("storeFile"))
                storePassword = p.getProperty("storePassword")
                keyAlias = p.getProperty("keyAlias")
                keyPassword = p.getProperty("keyPassword")
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
            signingConfig = signingConfigs.findByName("release")
        }
        debug {
            buildConfigField("boolean", "LOCAL_SERVER", "true")
            // QA only (-PjfMinify): optimise and rename as R8 does for release
            // (it won't for a debuggable build), keeping the local server, so the
            // emulator tour can run release-shaped code against it.
            if (providers.gradleProperty("jfMinify").isPresent) {
                isDebuggable = false
                isMinifyEnabled = true
                proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
            }
        }
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    packaging {
        resources.excludes += "/META-INF/{AL2.0,LGPL2.1}"
    }
}

kotlin {
    compilerOptions {
        jvmTarget.set(JvmTarget.JVM_17)
    }
}

dependencies {
    implementation(platform(libs.compose.bom))
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.browser)
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.lifecycle.process)
    implementation(libs.androidx.lifecycle.runtime.compose)
    implementation(libs.androidx.work)
    implementation(libs.compose.foundation)
    implementation(libs.compose.icons.extended)
    implementation(libs.compose.material3)
    implementation(libs.compose.ui)
    implementation(libs.compose.ui.tooling.preview)
    implementation(libs.glance.appwidget)
    implementation(libs.kotlinx.coroutines.android)
    implementation(libs.kotlinx.serialization.json)
    debugImplementation(libs.compose.ui.tooling)
    testImplementation(libs.junit)
}
