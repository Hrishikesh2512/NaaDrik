import org.gradle.api.tasks.Copy

plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.ktlint)
}

// The app reads the same config.yaml as the Python prototype; copy it in at build time.
val sharedConfig =
    tasks.register<Copy>("copySharedConfig") {
        from(rootProject.projectDir.parentFile.resolve("config.yaml"))
        into(layout.buildDirectory.dir("generated/naadrikAssets"))
    }

android {
    namespace = "com.naadrik.app"
    compileSdk = 37

    defaultConfig {
        applicationId = "com.naadrik.app"
        minSdk = 26
        targetSdk = 37
        versionCode = 3
        versionName = "1.0.0-alpha.1"
    }

    buildTypes {
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
            signingConfig = signingConfigs.getByName("debug")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    buildFeatures {
        compose = true
    }

    sourceSets["main"].assets.directories.add(
        layout.buildDirectory
            .dir("generated/naadrikAssets")
            .get()
            .asFile.path,
    )
}

tasks.named("preBuild") { dependsOn(sharedConfig) }

dependencies {
    implementation(project(":core"))
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.lifecycle.runtime.ktx)
    implementation(platform(libs.compose.bom))
    implementation(libs.compose.ui)
    implementation(libs.compose.material3)
    implementation(libs.compose.ui.tooling.preview)
}
