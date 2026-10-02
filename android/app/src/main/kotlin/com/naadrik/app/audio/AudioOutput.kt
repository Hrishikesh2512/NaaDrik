package com.naadrik.app.audio

import android.content.Context
import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioManager
import android.media.AudioTimestamp
import android.media.AudioTrack
import android.os.Process
import android.util.Log
import com.naadrik.app.LOG_TAG

/** Fills an interleaved stereo float buffer with the given number of frames. */
fun interface Renderer {
    fun render(
        frames: Int,
        out: FloatArray,
    )
}

/** The device's native output format: rendering at it avoids resampling on the fast path. */
data class DeviceAudio(
    val sampleRate: Int,
    val framesPerBurst: Int,
) {
    companion object {
        fun query(context: Context): DeviceAudio {
            val manager = context.getSystemService(AudioManager::class.java)
            val rate = manager.getProperty(AudioManager.PROPERTY_OUTPUT_SAMPLE_RATE)?.toIntOrNull() ?: 48000
            val burst = manager.getProperty(AudioManager.PROPERTY_OUTPUT_FRAMES_PER_BUFFER)?.toIntOrNull() ?: 256
            return DeviceAudio(rate, burst)
        }
    }
}

/**
 * Low-latency AudioTrack driven by a dedicated urgent-priority thread.
 *
 * The buffer starts at two bursts and grows by one burst whenever an underrun is detected,
 * the same latency tuning Oboe applies, so it settles at the smallest glitch-free size.
 */
class AudioOutput(
    private val device: DeviceAudio,
    private val renderer: Renderer,
) {
    private val burst = device.framesPerBurst
    private val track: AudioTrack =
        AudioTrack
            .Builder()
            .setAudioAttributes(
                AudioAttributes
                    .Builder()
                    .setUsage(AudioAttributes.USAGE_MEDIA)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
                    .build(),
            ).setAudioFormat(
                AudioFormat
                    .Builder()
                    .setEncoding(AudioFormat.ENCODING_PCM_FLOAT)
                    .setSampleRate(device.sampleRate)
                    .setChannelMask(AudioFormat.CHANNEL_OUT_STEREO)
                    .build(),
            ).setPerformanceMode(AudioTrack.PERFORMANCE_MODE_LOW_LATENCY)
            .setTransferMode(AudioTrack.MODE_STREAM)
            .setBufferSizeInBytes(
                maxOf(
                    AudioTrack.getMinBufferSize(device.sampleRate, AudioFormat.CHANNEL_OUT_STEREO, AudioFormat.ENCODING_PCM_FLOAT),
                    burst * 8 * BYTES_PER_FRAME,
                ),
            ).build()

    val stats = OutputStats(device.sampleRate, burst)

    @Volatile private var running = false
    private var thread: Thread? = null
    private var framesWritten = 0L
    private val timestamp = AudioTimestamp()

    val fastPath: Boolean get() = track.performanceMode == AudioTrack.PERFORMANCE_MODE_LOW_LATENCY
    val bufferFrames: Int get() = track.bufferSizeInFrames

    fun start() {
        track.bufferSizeInFrames = 2 * burst
        running = true
        track.play()
        thread =
            Thread({ loop() }, "naadrik-audio").apply {
                start()
            }
        Log.i(LOG_TAG, "audio started: ${device.sampleRate} Hz, burst $burst, buffer ${track.bufferSizeInFrames}, fast path $fastPath")
    }

    fun stop() {
        running = false
        thread?.join(1000)
        thread = null
        track.pause()
        track.flush()
        track.stop()
        track.release()
    }

    /** Seconds until a frame written now reaches the speaker or headphones, from DAC timestamps. */
    fun outputLatencyS(): Double? {
        if (!track.getTimestamp(timestamp)) return null
        val queuedS = (framesWritten - timestamp.framePosition).toDouble() / device.sampleRate
        val sinceS = (System.nanoTime() - timestamp.nanoTime) / 1e9
        return (queuedS - sinceS).takeIf { it > 0 }
    }

    private fun loop() {
        Process.setThreadPriority(Process.THREAD_PRIORITY_URGENT_AUDIO)
        val buffer = FloatArray(burst * 2)
        var lastUnderruns = track.underrunCount
        while (running) {
            val started = System.nanoTime()
            renderer.render(burst, buffer)
            stats.recordRender(System.nanoTime() - started)
            val written = track.write(buffer, 0, buffer.size, AudioTrack.WRITE_BLOCKING)
            if (written < 0) {
                Log.e(LOG_TAG, "AudioTrack.write failed: $written")
                break
            }
            framesWritten += written / 2
            val underruns = track.underrunCount
            if (underruns > lastUnderruns) {
                stats.underruns += underruns - lastUnderruns
                lastUnderruns = underruns
                val grown = minOf(track.bufferSizeInFrames + burst, track.bufferCapacityInFrames)
                track.bufferSizeInFrames = grown
                Log.w(LOG_TAG, "underrun: buffer grown to $grown frames")
            }
        }
    }

    private companion object {
        const val BYTES_PER_FRAME = 8 // stereo float
    }
}

/** Render-time statistics, written by the audio thread and read by the UI. */
class OutputStats(
    private val sampleRate: Int,
    private val burst: Int,
) {
    private val renderNanos = LongArray(4096)
    private var count = 0

    @Volatile var underruns = 0

    fun recordRender(nanos: Long) {
        renderNanos[count % renderNanos.size] = nanos
        count++
    }

    fun reset() {
        count = 0
        underruns = 0
    }

    /** (mean ms, p95 ms, max ms, blocks) over the most recent blocks. */
    fun summary(): RenderSummary {
        val n = minOf(count, renderNanos.size)
        if (n == 0) return RenderSummary(0.0, 0.0, 0.0, 0, burst * 1000.0 / sampleRate)
        val sorted = renderNanos.copyOf(n).sorted()
        return RenderSummary(
            sorted.average() / 1e6,
            sorted[(n * 95 / 100).coerceAtMost(n - 1)] / 1e6,
            sorted.last() / 1e6,
            count,
            burst * 1000.0 / sampleRate,
        )
    }
}

data class RenderSummary(
    val meanMs: Double,
    val p95Ms: Double,
    val maxMs: Double,
    val blocks: Int,
    val budgetMs: Double,
)
