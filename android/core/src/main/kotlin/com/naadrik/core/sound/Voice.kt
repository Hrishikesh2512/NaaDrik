package com.naadrik.core.sound

import com.naadrik.core.config.Config
import kotlin.math.ceil
import kotlin.math.exp
import kotlin.math.ln
import kotlin.math.max
import kotlin.math.min

/** A voice sounds one object: it pulses notes at the object's rate and places them in space. */
class Voice(
    private val bank: NoteBank,
    config: Config,
    params: SoundParams,
    maxBlock: Int,
) {
    private class NoteEvent {
        var degree = 0
        var levels = Levels(0.0, 0.0, 0.0)
        var end = 0
        var offset = 0
        var position = 0
        var active = false
    }

    private val pulse = config.pulse
    private val sr = bank.sampleRate
    private val smoothingSamples = config.spatial.smoothingMs / 1000.0 * sr
    private val attack = max(1, (pulse.attackMs / 1000.0 * sr).toInt())
    private val release = max(1, (pulse.releaseMs / 1000.0 * sr).toInt())
    private val spatialiser = Spatialiser(config.spatial, sr, maxBlock)
    private val mono = DoubleArray(maxBlock)

    // Gate <= duty x period < period, so at most two notes overlap (one releasing); four is ample.
    private val events = Array(EVENT_POOL) { NoteEvent() }

    var target: SoundParams = params
    var azimuthDeg = params.azimuthDeg
        private set
    var pulseHz = params.pulseHz
        private set
    private var phase = 1.0 // sound the first pulse immediately rather than after a full period
    private var released = false

    val finished: Boolean get() = released && events.none { it.active }

    fun release() {
        released = true
    }

    /** Add [n] frames of this voice to interleaved stereo [out]. */
    fun render(
        n: Int,
        out: FloatArray,
    ) {
        glide(n)
        if (!released) schedulePulses(n)
        mono.fill(0.0, 0, n)
        for (event in events) if (event.active) renderEvent(event, n)
        spatialiser.process(mono, n, azimuthDeg, out)
    }

    private fun glide(n: Int) {
        val keep = if (smoothingSamples > 0) exp(-n / smoothingSamples) else 0.0
        azimuthDeg = target.azimuthDeg + (azimuthDeg - target.azimuthDeg) * keep
        // Glide the rate in the log domain, matching how distance maps to rate.
        pulseHz = exp(ln(target.pulseHz) + (ln(pulseHz) - ln(target.pulseHz)) * keep)
    }

    private fun schedulePulses(n: Int) {
        val step = pulseHz / sr
        var position = 0
        while (true) {
            val toNext = max(0, ceil((1.0 - phase) / step).toInt())
            if (position + toNext >= n) {
                phase += step * (n - position)
                return
            }
            position += toNext
            phase = 0.0
            startNote(position)
        }
    }

    private fun startNote(offset: Int) {
        val event = events.firstOrNull { !it.active } ?: return
        val gate = (min(pulse.dutyCycle / pulseHz, pulse.maxGateS) * sr).toInt()
        event.degree = target.degree
        event.levels = target.levels
        event.end = min(gate + release, bank.noteLength)
        event.offset = offset
        event.position = 0
        event.active = true
    }

    private fun renderEvent(
        event: NoteEvent,
        n: Int,
    ) {
        val count = min(n - event.offset, event.end - event.position)
        for (j in 0 until count) {
            val index = event.position + j
            val attackGain = min(index.toDouble() / attack, 1.0)
            val releaseGain = ((event.end - index).toDouble() / release).coerceIn(0.0, 1.0)
            mono[event.offset + j] += bank.sample(event.degree, event.levels, index) * attackGain * releaseGain
        }
        event.position += max(count, 0)
        event.offset = 0
        if (event.position >= event.end) event.active = false
    }

    private companion object {
        const val EVENT_POOL = 4
    }
}
