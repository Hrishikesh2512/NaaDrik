# Naadrik for Android

Kotlin app, `com.naadrik.app`, minSdk 26 (Android 8.0), targetSdk 37. Fully offline.

| Module | Contents |
|---|---|
| `core` | Plain Kotlin (JVM) library: config loader and the sound engine, a port of the Python v0.4.1 engine including the presence hum. Unit-tested on the JVM. |
| `app` | Android app: low-latency audio output, UI. |

The app reads the repository's `config.yaml` (copied into the APK's assets at build time), so the
phone and the Python prototype use the same mapping values. `core` tests check the Kotlin
mapping against reference values exported from Python (`scripts/export_parity_fixture.py`).

## Build

Needs JDK 17+ and the Android SDK (`sdk.dir` in `android/local.properties`, or `ANDROID_HOME`).
Android Studio can open the `android/` folder directly.

```bash
cd android
./gradlew ktlintCheck :core:test :app:lintDebug   # style, unit tests, Android lint
./gradlew :app:assembleRelease                     # app/build/outputs/apk/release/app-release.apk
```

Release builds are minified and, until a release key exists, signed with the debug key so they
can be side-loaded for testing.

## Install on a phone

1. On the phone: Settings → About phone → Software information → tap **Build number** seven
   times, then Settings → Developer options → enable **USB debugging**.
2. Connect it by USB and accept the "Allow USB debugging" prompt.
3. `adb install -r app/build/outputs/apk/release/app-release.apk`

Logs: `adb logcat -s Naadrik`. Lines starting `REPORT` summarise the device and the engine test.
