package com.naadrik.core

import com.naadrik.core.sound.ObjectState
import com.naadrik.core.sound.SoundEngine
import com.naadrik.core.sound.Voice
import com.naadrik.core.sound.staggeredPhase
import kotlin.math.abs
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class PulseStaggerTest {
    private val config = TestSupport.config
    private val sr = 48000
    private val engine by lazy { SoundEngine(config, sr) }
    private val obj = ObjectState(0.5, 0.5, 0.2, 1.0, 0.0, 0.0)

    private fun voiceAt(
        phase: Double,
        state: ObjectState = obj,
    ) = Voice(engine.bank, config, engine.map(state), engine.maxBlock, phase)

    private val rate get() = engine.map(obj).pulseHz

    @Test
    fun `alone a voice starts immediately`() {
        assertEquals(1.0, staggeredPhase(rate, emptyList()))
    }

    @Test
    fun `second voice lands halfway between the first one's pulses`() {
        assertEquals(0.5, staggeredPhase(rate, listOf(voiceAt(1.0))), 1e-12)
        assertEquals(0.7, staggeredPhase(rate, listOf(voiceAt(0.2))), 1e-12)
    }

    @Test
    fun `third voice takes the largest remaining gap`() {
        val phase = staggeredPhase(rate, listOf(voiceAt(0.0), voiceAt(0.5)))
        assertTrue(abs(phase - 0.25) < 1e-12 || abs(phase - 0.75) < 1e-12, "got $phase")
    }

    @Test
    fun `voices at clearly different rates are not staggered`() {
        val far = obj.copy(distance = 1.0)
        assertEquals(1.0, staggeredPhase(rate, listOf(voiceAt(1.0, far))))
    }

    @Test
    fun `two equal objects created together pulse half a period apart`() {
        val left = engine.createVoice(obj.copy(x = 0.1))
        val right = engine.createVoice(obj.copy(x = 0.9), listOf(left))

        fun firstOnsetFrame(voice: Voice): Int {
            val out = FloatArray(2 * sr)
            var start = 0
            while (start + 256 <= sr) {
                val chunk = FloatArray(512)
                voice.render(256, chunk)
                chunk.copyInto(out, start * 2)
                start += 256
            }
            return (0 until sr).first { abs(out[2 * it]) + abs(out[2 * it + 1]) > 1e-4 }
        }

        val offsetS = (firstOnsetFrame(right) - firstOnsetFrame(left)).toDouble() / sr
        assertEquals(0.5 / rate, offsetS, 0.01)
    }
}
