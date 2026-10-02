package com.naadrik.core

import com.naadrik.core.sound.LiveMixer
import com.naadrik.core.sound.ObjectState
import com.naadrik.core.sound.Part
import com.naadrik.core.sound.SCENARIOS
import com.naadrik.core.sound.Scenario
import com.naadrik.core.sound.SoundEngine
import com.naadrik.core.sound.bowedNote
import com.naadrik.core.sound.fluteNote
import com.naadrik.core.sound.pluckNote
import com.naadrik.core.sound.presenceNote
import java.util.Random
import kotlin.math.abs
import kotlin.math.sqrt
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class SoundEngineTest {
    private val config = TestSupport.config
    private val sr = 48000
    private val engine by lazy { SoundEngine(config, sr) }

    @Test
    fun `instruments are in tune`() {
        val inst = config.instruments
        for (freq in listOf(196.0, 440.0, 1046.5)) {
            val notes =
                mapOf(
                    "pluck" to pluckNote(freq, sr, 0.5, inst.pluck, Random(0)),
                    "bowed" to bowedNote(freq, sr, 0.5, inst.bowed, Random(0)),
                    "flute" to fluteNote(freq, sr, 0.5, inst.flute, Random(0)),
                    "presence" to presenceNote(freq, sr, 0.5, inst.presence, Random(0)),
                )
            for ((name, note) in notes) {
                val segment = note.copyOfRange((0.05 * sr).toInt(), (0.25 * sr).toInt())
                val error = abs(cents(estimateF0(segment, sr), freq))
                assertTrue(error < 20, "$name at $freq Hz is $error cents off")
            }
        }
    }

    @Test
    fun `pluck decays`() {
        val note = pluckNote(220.0, sr, 1.0, config.instruments.pluck, Random(0))

        fun rms(
            a: Int,
            b: Int,
        ) = sqrt((a until b).sumOf { note[it] * note[it] } / (b - a))
        assertTrue(rms(sr - sr / 5, sr) < rms(0, sr / 10) / 3)
    }

    @Test
    fun `render object is bounded stereo`() {
        val out = engine.renderObject(ObjectState(0.2, 0.3, 0.5, 1.0, 0.5, 0.0), 1.0)
        assertEquals(2 * sr, out.size)
        assertTrue(out.all { it.isFinite() && abs(it) <= 1f })
    }

    @Test
    fun `every colour is audible including black`() {
        val values = listOf(0.0, 0.4, 1.0)
        for (r in values) {
            for (g in values) {
                for (b in values) {
                    val (left, right) = channelRms(engine.renderObject(ObjectState(0.5, 0.5, 0.0, r, g, b), 0.3))
                    assertTrue(left + right > 0.02, "rgb=($r,$g,$b) is too quiet")
                }
            }
        }
    }

    @Test
    fun `brightness orders loudness`() {
        fun loudness(
            r: Double,
            g: Double,
            b: Double,
        ) = channelRms(engine.renderObject(ObjectState(0.5, 0.5, 0.2, r, g, b), 1.0)).let { it.first + it.second }
        val black = loudness(0.0, 0.0, 0.0)
        val darkRed = loudness(0.4, 0.0, 0.0)
        val red = loudness(1.0, 0.0, 0.0)
        val white = loudness(1.0, 1.0, 1.0)
        assertTrue(black < darkRed && darkRed < red && red < white, "$black $darkRed $red $white")
    }

    @Test
    fun `pulse rate follows distance for every colour`() {
        for (rgb in listOf(Triple(0.0, 0.0, 1.0), Triple(0.0, 0.0, 0.0))) {
            val near = engine.renderObject(ObjectState(0.5, 0.5, 0.0, rgb.first, rgb.second, rgb.third), 3.0)
            val far = engine.renderObject(ObjectState(0.5, 0.5, 1.0, rgb.first, rgb.second, rgb.third), 3.0)
            assertEquals(24.0, countPulses(near, sr).toDouble(), 1.0)
            assertEquals(3.0, countPulses(far, sr).toDouble(), 1.0)
        }
    }

    @Test
    fun `position sets the louder ear`() {
        val (l1, r1) = channelRms(engine.renderObject(ObjectState(0.0, 0.5, 0.3, 0.0, 1.0, 0.0), 1.0))
        assertTrue(l1 > 1.5 * r1)
        val (l2, r2) = channelRms(engine.renderObject(ObjectState(1.0, 0.5, 0.3, 0.0, 0.0, 0.0), 1.0))
        assertTrue(r2 > 1.5 * l2)
    }

    @Test
    fun `height sets pitch for a black object`() {
        fun pitch(y: Double): Double {
            val m = mono(engine.renderObject(ObjectState(0.5, y, 1.0, 0.0, 0.0, 0.0), 0.3))
            return estimateF0(m.copyOfRange(2400, 14400), sr)
        }
        assertTrue(pitch(0.0) > 3 * pitch(1.0))
    }

    @Test
    fun `moving object has no clicks`() {
        val moving = engine.renderPaths(listOf { t -> ObjectState(t / 2.0, 0.5, 0.3, 0.0, 0.0, 1.0) }, 2.0)
        val still = engine.renderObject(ObjectState(0.0, 0.5, 0.3, 0.0, 0.0, 1.0), 2.0)

        fun maxStep(a: FloatArray) = (2 until a.size).maxOf { abs(a[it] - a[it - 2]) }
        assertTrue(maxStep(moving) < 1.5 * maxStep(still))
    }

    @Test
    fun `all demo scenarios render`() {
        for (scenario in SCENARIOS) {
            val out = engine.renderParts(scenario.parts, 0.5)
            assertTrue(out.any { it != 0f }, scenario.name)
        }
    }

    @Test
    fun `versus scenarios play left alone, then right alone, then both`() {
        val scenario = SCENARIOS.first { it.name == "Black versus white" }
        val out = engine.renderParts(scenario.parts, scenario.durationS)
        val solo = Scenario.VERSUS_SOLO_S
        val gap = Scenario.VERSUS_GAP_S

        fun window(
            fromS: Double,
            toS: Double,
        ): Pair<Double, Double> = channelRms(out.copyOfRange((fromS * sr).toInt() * 2, (toS * sr).toInt() * 2))

        val (leftL, leftR) = window(0.1, solo - 0.1)
        val (rightL, rightR) = window(solo + gap + 0.1, 2 * solo + gap - 0.1)
        val (bothL, bothR) = window(2 * (solo + gap) + 0.1, scenario.durationS - 0.1)
        assertTrue(leftL > 1.5 * leftR, "first segment must come from the left")
        assertTrue(rightR > 1.5 * rightL, "second segment must come from the right")
        assertTrue(rightL + rightR > 2 * (leftL + leftR), "white must be clearly louder than black")
        assertTrue(bothL > 0.02 && bothR > 0.02, "both sound in the last segment")
        val (gapL, gapR) = window(solo + 0.4, solo + gap - 0.05)
        assertTrue(gapL + gapR < 0.2 * (leftL + leftR), "the pause between segments is near-silent")
    }

    @Test
    fun `timeline never sounds more than max objects at once`() {
        val parts = (1..6).map { Part({ _ -> ObjectState(0.5, 0.5, 0.0, 1.0, 0.0, 0.0) }) }
        val capped = engine.renderParts(parts, 0.3)
        val three = engine.renderParts(parts.take(config.objects.maxObjects), 0.3)
        assertTrue(capped.contentEquals(three))
    }

    @Test
    fun `live mixer creates caps and releases voices`() {
        var applied = 0L
        val mixer = LiveMixer(engine) { applied = it }
        val out = FloatArray(512)
        mixer.render(256, out)
        assertTrue(out.all { it == 0f })
        val red = ObjectState(0.2, 0.3, 0.0, 1.0, 0.0, 0.0)
        mixer.update((1..10).associateWith { red }, captureNanos = 42L)
        mixer.render(256, out)
        assertEquals(config.objects.maxObjects, mixer.activeIds.size)
        assertEquals(42L, applied)
        assertTrue(out.any { it != 0f })
        mixer.update(emptyMap(), 43L)
        repeat(50) { mixer.render(256, out) }
        assertTrue(mixer.activeIds.isEmpty())
        assertTrue(out.all { it == 0f }, "released voices must ring out and stop")
    }

    @Test
    fun `three voices render well inside the block budget`() {
        val mixer = LiveMixer(engine)
        mixer.update(
            mapOf(
                1 to ObjectState(0.1, 0.3, 0.0, 1.0, 1.0, 1.0),
                2 to ObjectState(0.5, 0.5, 0.5, 0.0, 1.0, 0.0),
                3 to ObjectState(0.9, 0.8, 1.0, 0.0, 0.0, 1.0),
            ),
            0L,
        )
        val out = FloatArray(512)
        repeat(500) { mixer.render(256, out) }
        val start = System.nanoTime()
        val blocks = 2000
        repeat(blocks) { mixer.render(256, out) }
        val perBlockMs = (System.nanoTime() - start) / 1e6 / blocks
        println("JVM: 3 voices, 256-frame block: %.3f ms of %.3f ms budget".format(perBlockMs, 256 * 1000.0 / sr))
        assertTrue(perBlockMs < 256 * 1000.0 / sr / 2)
    }
}
