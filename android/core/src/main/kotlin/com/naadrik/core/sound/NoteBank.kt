package com.naadrik.core.sound

import com.naadrik.core.config.Config
import java.util.Random
import kotlin.math.sqrt

/**
 * Pre-rendered notes. Pitch is quantised to a scale, so the set is small and fixed; rendering
 * it once keeps the audio thread to multiply-adds over stored arrays.
 */
class NoteBank(
    config: Config,
    val sampleRate: Int,
    seed: Long = 7L,
) {
    val frequencies: DoubleArray = scaleFrequencies(config.pitch)
    val nDegrees: Int get() = frequencies.size
    val presenceLevel: Float =
        config.instruments.presence.level
            .toFloat()

    /** [instrument][degree] for pluck, bowed, flute; already scaled by each instrument's gain. */
    val notes: Array<Array<FloatArray>>
    val presence: Array<FloatArray>
    val noteLength: Int

    init {
        val inst = config.instruments
        val rng = Random(seed)
        val duration = inst.noteDurationS
        notes =
            arrayOf(
                Array(nDegrees) { render(pluckNote(frequencies[it], sampleRate, duration, inst.pluck, rng), inst.pluck.gain) },
                Array(nDegrees) { render(bowedNote(frequencies[it], sampleRate, duration, inst.bowed, rng), inst.bowed.gain) },
                Array(nDegrees) { render(fluteNote(frequencies[it], sampleRate, duration, inst.flute, rng), inst.flute.gain) },
            )
        presence = Array(nDegrees) { render(presenceNote(frequencies[it], sampleRate, duration, inst.presence, rng), 1.0) }
        noteLength = presence[0].size
    }

    private fun render(
        note: DoubleArray,
        gain: Double,
    ): FloatArray {
        // Equalise loudness over the audible gate window, then guarantee no sample exceeds 1.
        val window = minOf(note.size, (LOUDNESS_WINDOW_S * sampleRate).toInt())
        var sumSq = 0.0
        for (i in 0 until window) sumSq += note[i] * note[i]
        var scale = TARGET_RMS / (sqrt(sumSq / window) + 1e-12)
        val peak = note.peakAbs() * scale
        if (peak > 1.0) scale /= peak
        return FloatArray(note.size) { (note[it] * scale * gain).toFloat() }
    }

    /** One sample of the presence hum plus colour instruments: what a voice plays. */
    fun sample(
        degree: Int,
        levels: Levels,
        index: Int,
    ): Float =
        presenceLevel * presence[degree][index] +
            levels.pluck.toFloat() * notes[0][degree][index] +
            levels.bowed.toFloat() * notes[1][degree][index] +
            levels.flute.toFloat() * notes[2][degree][index]

    private companion object {
        const val LOUDNESS_WINDOW_S = 0.3
        const val TARGET_RMS = 0.2
    }
}
