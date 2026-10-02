package com.naadrik.app.demo

import android.content.Context
import android.content.pm.PackageManager
import android.media.AudioManager
import android.os.Build
import com.naadrik.app.audio.DeviceAudio

/** One-line facts about the phone that decide audio and model choices. */
fun deviceReport(
    context: Context,
    audio: DeviceAudio,
): List<String> {
    val pm = context.packageManager
    val lines =
        mutableListOf(
            "device ${Build.MANUFACTURER} ${Build.MODEL} (${Build.DEVICE}), Android ${Build.VERSION.RELEASE} / API ${Build.VERSION.SDK_INT}",
            "hardware ${Build.HARDWARE}, ABIs ${Build.SUPPORTED_ABIS.joinToString()}, cores ${Runtime.getRuntime().availableProcessors()}",
            "audio native ${audio.sampleRate} Hz, burst ${audio.framesPerBurst} frames " +
                "(%.1f ms)".format(audio.framesPerBurst * 1000.0 / audio.sampleRate),
            "feature low_latency=${pm.hasSystemFeature(PackageManager.FEATURE_AUDIO_LOW_LATENCY)} " +
                "pro=${pm.hasSystemFeature(PackageManager.FEATURE_AUDIO_PRO)}",
        )
    if (Build.VERSION.SDK_INT >= 33) {
        val spatializer = context.getSystemService(AudioManager::class.java).spatializer
        lines += "spatializer level=${spatializer.immersiveAudioLevel} " +
            "available=${spatializer.isAvailable} enabled=${spatializer.isEnabled}"
    } else {
        lines += "spatializer unavailable before Android 13; using Naadrik's own head model"
    }
    return lines
}
