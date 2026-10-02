package com.naadrik.app

import android.content.Context
import com.naadrik.app.audio.DeviceAudio
import com.naadrik.core.config.Config
import com.naadrik.core.sound.SoundEngine
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext

/**
 * The shared config and sound engine, built once per process. Building the note bank takes a
 * moment, so it happens off the main thread and both the demo and live mode reuse it.
 */
object EngineProvider {
    private val lock = Mutex()
    private var engine: SoundEngine? = null

    @Volatile var buildMs = 0.0
        private set

    suspend fun get(context: Context): SoundEngine =
        lock.withLock {
            engine ?: withContext(Dispatchers.Default) {
                val started = System.nanoTime()
                val yaml =
                    context.assets
                        .open("config.yaml")
                        .bufferedReader()
                        .use { it.readText() }
                val device = DeviceAudio.query(context)
                SoundEngine(Config.parse(yaml), sampleRate = device.sampleRate).also {
                    buildMs = (System.nanoTime() - started) / 1e6
                    engine = it
                }
            }
        }
}
