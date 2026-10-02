package com.naadrik.core

import com.naadrik.core.sound.distanceToPulseRate
import com.naadrik.core.sound.earAlphas
import com.naadrik.core.sound.headShadowCoefficients
import com.naadrik.core.sound.heightToDegree
import com.naadrik.core.sound.interauralTimeDifference
import com.naadrik.core.sound.quantiseChannel
import com.naadrik.core.sound.rgbToLevels
import com.naadrik.core.sound.scaleFrequencies
import com.naadrik.core.sound.softClip
import com.naadrik.core.sound.xToAzimuth
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.double
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonPrimitive
import java.io.File
import kotlin.test.Test
import kotlin.test.assertEquals

/** The Kotlin engine must reproduce the Python v0.4.1 mapping exactly (fixture from scripts/). */
class ParityTest {
    private val fixture: JsonObject =
        Json.parseToJsonElement(File(javaClass.getResource("/parity.json")!!.toURI()).readText()) as JsonObject
    private val config = TestSupport.config
    private val tolerance = 1e-9

    private fun cases(key: String): List<JsonArray> = fixture[key]!!.jsonArray.map { it.jsonArray }

    private fun JsonArray.d(i: Int) = this[i].jsonPrimitive.double

    @Test
    fun `scale frequencies`() {
        val expected = fixture["scale_frequencies"]!!.jsonArray.map { it.jsonPrimitive.double }
        val actual = scaleFrequencies(config.pitch).toList()
        assertEquals(expected.size, actual.size)
        expected.zip(actual).forEach { (e, a) -> assertEquals(e, a, tolerance) }
    }

    @Test
    fun `height to degree`() {
        val n = scaleFrequencies(config.pitch).size
        for (c in cases("height_to_degree")) assertEquals(c[1].jsonPrimitive.int, heightToDegree(c.d(0), n), "y=${c.d(0)}")
    }

    @Test
    fun `distance to pulse rate`() {
        for (c in cases("distance_to_pulse_rate")) assertEquals(c.d(1), distanceToPulseRate(c.d(0), config.pulse), tolerance)
    }

    @Test
    fun `colour quantisation and levels`() {
        for (c in cases("quantise_channel")) assertEquals(c[1].jsonPrimitive.int, quantiseChannel(c.d(0), config.colour))
        for (c in cases("rgb_to_levels")) {
            val rgb = c[0].jsonArray.map { it.jsonPrimitive.double }
            val expected = c[1].jsonArray.map { it.jsonPrimitive.double }
            val levels = rgbToLevels(rgb[0], rgb[1], rgb[2], config.colour)
            assertEquals(expected, listOf(levels.pluck, levels.bowed, levels.flute), "rgb=$rgb")
        }
    }

    @Test
    fun `azimuth and itd`() {
        for (c in cases("x_to_azimuth")) assertEquals(c.d(1), xToAzimuth(c.d(0), config.spatial), tolerance)
        for (c in cases("itd")) assertEquals(c.d(1), interauralTimeDifference(c.d(0), config.spatial.headRadiusM), tolerance)
    }

    @Test
    fun `head shadow`() {
        for (c in cases("ear_alphas")) {
            val (left, right) = earAlphas(c.d(0))
            val expected = c[1].jsonArray.map { it.jsonPrimitive.double }
            assertEquals(expected[0], left, tolerance)
            assertEquals(expected[1], right, tolerance)
        }
        for (c in cases("head_shadow")) {
            val coefficients = headShadowCoefficients(c.d(0), 0.0875, config.audio.sampleRate)
            val b = c[1].jsonArray.map { it.jsonPrimitive.double }
            val a = c[2].jsonArray.map { it.jsonPrimitive.double }
            assertEquals(b[0], coefficients[0], tolerance)
            assertEquals(b[1], coefficients[1], tolerance)
            assertEquals(a[1], coefficients[2], tolerance)
        }
    }

    @Test
    fun `soft clip`() {
        for (c in cases("soft_clip")) assertEquals(c.d(1), softClip(c.d(0)), tolerance)
    }
}
