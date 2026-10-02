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
    ): FloatArray {
        val limited = paths.take(config.objects.maxObjects)
        val block = config.audio.blockSize
        val total = (durationS * sampleRate).toInt()
        val voices = limited.map { createVoice(it(0.0)) }
        val out = FloatArray(total * 2)
        val scratch = FloatArray(block * 2)
        var start = 0
        while (start < total) {
            val n = minOf(block, total - start)
            scratch.fill(0f)
            val t = start.toDouble() / sampleRate
            voices.forEachIndexed { i, voice ->
                voice.target = map(limited[i](t))
                voice.render(n, scratch)
            }
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
