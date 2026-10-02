package com.naadrik.core.sound

import com.naadrik.core.config.Config
import kotlin.math.abs
import kotlin.math.sign
import kotlin.math.tanh

private const val LIMITER_KNEE = 0.8

/** Linear below the knee, then a tanh shoulder that never exceeds 1. */
fun softClip(
    x: Double,
    knee: Double = LIMITER_KNEE,
): Double {
    val magnitude = abs(x)
    if (magnitude <= knee) return x
    return sign(x) * (knee + (1.0 - knee) * tanh((magnitude - knee) / (1.0 - knee)))
}

/** A sound that plays from [startS] until [endS] (seconds), then rings out. */
class Part(
    val path: (Double) -> ObjectState,
    val startS: Double = 0.0,
    val endS: Double = Double.POSITIVE_INFINITY,
)

/**
 * Public sound-engine API. [sampleRate] defaults to the config but on Android is the device's
 * native output rate, so audio never passes through a resampler.
 */
class SoundEngine(
    val config: Config,
    val sampleRate: Int = config.audio.sampleRate,
    val maxBlock: Int = 4096,
) {
    val bank = NoteBank(config, sampleRate)

    fun map(obj: ObjectState): SoundParams = mapObject(config, bank.nDegrees, obj)

    fun createVoice(obj: ObjectState): Voice = Voice(bank, config, map(obj), maxBlock)

    /** Render one static object to interleaved stereo float samples. */
    fun renderObject(
        obj: ObjectState,
        durationS: Double = 2.0,
    ): FloatArray = renderPaths(listOf { _ -> obj }, durationS)

    /** Render objects whose state changes over time; each path maps seconds to a state. */
    fun renderPaths(
        paths: List<(Double) -> ObjectState>,
        durationS: Double,
    ): FloatArray = renderParts(paths.map { Part(it) }, durationS)

    /**
     * Render a timeline of parts. At most `max_objects` parts sound at once; a part that ends
     * is released so its last note rings out naturally.
     */
    fun renderParts(
        parts: List<Part>,
        durationS: Double,
    ): FloatArray {
        val block = config.audio.blockSize
        val total = (durationS * sampleRate).toInt()
        val voices = arrayOfNulls<Voice>(parts.size)
        val releasing = ArrayList<Voice>()
        val out = FloatArray(total * 2)
        val scratch = FloatArray(block * 2)
        var start = 0
        while (start < total) {
            val n = minOf(block, total - start)
            val t = start.toDouble() / sampleRate
            scratch.fill(0f)
            parts.forEachIndexed { i, part ->
                val voice = voices[i]
                val active = t >= part.startS && t < part.endS
                if (voice == null && active && voices.count { it != null } < config.objects.maxObjects) {
                    voices[i] = createVoice(part.path(t))
                } else if (voice != null && !active) {
                    voice.release()
                    releasing += voice
                    voices[i] = null
                }
                voices[i]?.let {
                    it.target = map(part.path(t))
                    it.render(n, scratch)
                }
            }
            for (voice in releasing) voice.render(n, scratch)
            releasing.removeAll { it.finished }
            scratch.copyInto(out, start * 2, 0, n * 2)
            start += n
        }
        master(out, total)
        return out
    }

    /** Master gain and soft limiter, in place over [frames] interleaved stereo frames. */
    fun master(
        buffer: FloatArray,
        frames: Int,
    ) {
        val gain = config.audio.masterGain
        for (i in 0 until frames * 2) buffer[i] = softClip(buffer[i] * gain).toFloat()
    }
}
