import org.gradle.api.DefaultTask
import org.gradle.api.file.DirectoryProperty
import org.gradle.api.provider.MapProperty
import org.gradle.api.tasks.Copy
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.OutputDirectory
import org.gradle.api.tasks.TaskAction
import java.net.URI
import java.security.MessageDigest

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

/**
 * Downloads the on-device models once, verifying each checksum. They are not committed; the
 * files land in android/models (git-ignored) and are packaged as uncompressed assets.
 */
abstract class DownloadModels : DefaultTask() {
    /** file name -> "url sha256" */
    @get:Input
    abstract val models: MapProperty<String, String>

    @get:OutputDirectory
    abstract val outputDir: DirectoryProperty

    @TaskAction
    fun download() {
        for ((name, spec) in models.get()) {
            val (url, sha256) = spec.split(" ")
            val target = outputDir.file(name).get().asFile
            if (target.isFile && digest(target.readBytes()) == sha256) continue
            logger.lifecycle("Downloading $name")
            val bytes = URI(url).toURL().openStream().use { it.readBytes() }
            val actual = digest(bytes)
            check(actual == sha256) { "Checksum mismatch for $name: expected $sha256, got $actual" }
            target.writeBytes(bytes)
        }
    }

    private fun digest(bytes: ByteArray) = MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }
}

val downloadModels =
    tasks.register<DownloadModels>("downloadModels") {
        outputDir.set(rootProject.layout.projectDirectory.dir("models"))
        models.put(
            "efficientdet_lite0_int8.tflite",
            "https://storage.googleapis.com/mediapipe-models/object_detector/efficientdet_lite0/int8/latest/" +
                "efficientdet_lite0.tflite 0720bf247bd76e6594ea28fa9c6f7c5242be774818997dbbeffc4da460c723bb",
        )
        models.put(
            "midas_v21_small_256.tflite",
            "https://github.com/isl-org/MiDaS/releases/download/v2_1/model_opt.tflite " +
                "93d871071edff1218973ce25ee27ce95ccd20450c70a55e1b89efa3f5a772cdd",
        )
    }

android {
    namespace = "com.naadrik.app"
    compileSdk = 37

    defaultConfig {
        applicationId = "com.naadrik.app"
        minSdk = 26
        targetSdk = 37
        versionCode = 4
        versionName = "1.0.0-alpha.2"
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

    // One APK per phone CPU family: native MediaPipe/LiteRT code for every ABI would add ~45 MB.
    splits {
        abi {
            isEnable = true
            reset()
            include("arm64-v8a", "armeabi-v7a")
            isUniversalApk = false
        }
    }

    sourceSets["main"].assets.directories.add(
        layout.buildDirectory
            .dir("generated/naadrikAssets")
            .get()
            .asFile.path,
    )
    sourceSets["main"].assets.directories.add(
        rootProject.layout.projectDirectory
            .dir("models")
            .asFile.path,
    )

    // Models are memory-mapped straight from the APK, which requires them to be stored uncompressed.
    androidResources {
        noCompress += "tflite"
    }
}

tasks.named("preBuild") { dependsOn(sharedConfig, downloadModels) }

dependencies {
    implementation(project(":core"))
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.lifecycle.runtime.ktx)
    implementation(platform(libs.compose.bom))
    implementation(libs.compose.ui)
    implementation(libs.compose.material3)
    implementation(libs.compose.ui.tooling.preview)
    implementation(libs.camera.camera2)
    implementation(libs.camera.lifecycle)
    implementation(libs.camera.view)
    implementation(libs.mediapipe.tasks.vision)
    implementation(libs.litert)
    implementation(libs.litert.gpu)
    implementation(libs.litert.gpu.api)
    implementation(libs.arcore)
}
