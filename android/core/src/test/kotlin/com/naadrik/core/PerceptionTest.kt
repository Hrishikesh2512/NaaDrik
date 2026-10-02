package com.naadrik.core

import com.naadrik.core.perception.Box
import com.naadrik.core.perception.Calibration
import com.naadrik.core.perception.ColourSampler
import com.naadrik.core.perception.Detection
import com.naadrik.core.perception.DisparityMap
import com.naadrik.core.perception.DistanceNormaliser
import com.naadrik.core.perception.Frame
import com.naadrik.core.perception.FramePipeline
import com.naadrik.core.perception.LatencyMonitor
import com.naadrik.core.perception.Prioritiser
import com.naadrik.core.perception.RgbImage
import com.naadrik.core.perception.Track
import com.naadrik.core.perception.Tracker
import com.naadrik.core.perception.boxDisparity
import com.naadrik.core.perception.greyWorldGains
import com.naadrik.core.perception.levelToDistance
import com.naadrik.core.perception.motionFactor
import com.naadrik.core.perception.priorityScore
import com.naadrik.core.perception.quantiseDistance
import com.naadrik.core.sound.LiveMixer
import com.naadrik.core.sound.SoundEngine
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.double
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonPrimitive
import java.io.File
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue

class PerceptionTest {
    private val config = TestSupport.config
    private val fixture =
        Json.parseToJsonElement(File(javaClass.getResource("/parity.json")!!.toURI()).readText()) as JsonObject

    private fun rgb(
        r: Int,
        g: Int,
        b: Int,
    ) = (0xFF shl 24) or (r shl 16) or (g shl 8) or b

    private fun image(
        background: Int,
        patch: Int,
        w: Int = 100,
        h: Int = 100,
    ): RgbImage {
        val pixels = IntArray(w * h) { background }
        for (y in 40 until 60) for (x in 40 until 60) pixels[y * w + x] = patch
        return RgbImage(w, h, pixels)
    }

    // --- Parity with Python ------------------------------------------------------------

    @Test
    fun `priority matches python`() {
        for (case in fixture["priority"]!!.jsonArray.map { it.jsonArray }) {
            val label = case[0].jsonPrimitive.content
            val x = case[1].jsonPrimitive.double
            val distance = if (case[2] is JsonNull) null else case[2].jsonPrimitive.doubleOrNull
            val track = Track(1, label, 0.9, Box(x - 0.05, 0.4, x + 0.05, 0.5), 0.0)
            track.distance = distance
            track.distanceRate = case[3].jsonPrimitive.double
            track.velocityX = case[4].jsonPrimitive.double
            assertEquals(case[5].jsonPrimitive.double, priorityScore(track, config.priority), 1e-9, label)
            assertEquals(case[6].jsonPrimitive.double, motionFactor(track, config.priority), 1e-9, label)
        }
    }

    @Test
    fun `distance quantisation matches python`() {
        for (case in fixture["quantise_distance"]!!.jsonArray.map { it.jsonArray }) {
            val previous = if (case[1] is JsonNull) null else case[1].jsonPrimitive.int
            assertEquals(
                case[2].jsonPrimitive.int,
                quantiseDistance(case[0].jsonPrimitive.double, previous, 3, config.depth.hysteresis),
                "d=${case[0]} prev=$previous",
            )
        }
    }

    // --- Box, colour, distance ---------------------------------------------------------

    @Test
    fun `box geometry`() {
        val box = Box(0.2, 0.2, 0.6, 0.4)
        assertEquals(0.08, box.area, 1e-12)
        assertEquals(1.0, box.iou(box), 1e-12)
        assertEquals(0.0, box.iou(Box(0.7, 0.7, 0.9, 0.9)))
        val bounds = Box(0.999, 0.999, 1.0, 1.0).pixelBounds(10, 10)
        assertTrue(bounds[2] > bounds[0] && bounds[3] > bounds[1])
    }

    @Test
    fun `colour comes from the box centre not the background`() {
        val sampler = ColourSampler(config.colour.copy(whiteBalance = false))
        val (r, g, b) = sampler.sample(image(rgb(0, 0, 0), rgb(255, 0, 0)), Box(0.3, 0.3, 0.7, 0.7))
        assertEquals(1.0, r, 1e-9)
        assertEquals(0.0, g + b, 1e-9)
    }

    @Test
    fun `white balance removes casts and lifts dim scenes`() {
        val gains = greyWorldGains(RgbImage(2, 1, IntArray(2) { rgb(160, 120, 80) }))
        val balanced = doubleArrayOf(160 / 255.0 * gains[0], 120 / 255.0 * gains[1], 80 / 255.0 * gains[2])
        assertEquals(balanced.max(), balanced.min(), 1e-9)

        val sampler = ColourSampler(config.colour)
        val dim = image(rgb(20, 20, 20), rgb(60, 20, 20))
        sampler.updateWhiteBalance(dim)
        val (r, g, _) = sampler.sample(dim, Box(0.45, 0.45, 0.55, 0.55))
        assertTrue(r > config.colour.thresholds[1] && g < config.colour.thresholds[1])
    }

    private fun disparityMap(): DisparityMap {
        val values = FloatArray(100 * 100) { 1f }
        for (y in 10 until 40) for (x in 10 until 40) values[y * 100 + x] = 10f
        for (y in 60 until 90) for (x in 60 until 90) values[y * 100 + x] = 5f
        return DisparityMap(100, 100, values)
    }

    @Test
    fun `scene normalisation orders objects`() {
        val normaliser = DistanceNormaliser(config.depth.copy(normalisation = "scene"))
        val map = disparityMap()
        assertEquals(10.0, boxDisparity(map, Box(0.05, 0.05, 0.45, 0.45), 0.6), 1e-9)
        val near = normaliser.distance(map, Box(0.1, 0.1, 0.4, 0.4))
        val mid = normaliser.distance(map, Box(0.6, 0.6, 0.9, 0.9))
        val far = normaliser.distance(map, Box(0.45, 0.0, 0.55, 0.1))
        assertEquals(0.0, near, 1e-9)
        assertEquals(1.0, far, 1e-9)
        assertTrue(mid in near..far)
    }

    @Test
    fun `calibrated normalisation`() {
        val normaliser = DistanceNormaliser(config.depth.copy(normalisation = "calibrated"), Calibration(10.0, 2.0))
        assertEquals(5.0 / 8.0, normaliser.distance(disparityMap(), Box(0.6, 0.6, 0.9, 0.9)), 1e-9)
    }

    @Test
    fun `quantised levels map to sound distances`() {
        assertEquals(listOf(0.0, 0.5, 1.0), (0..2).map { levelToDistance(it, 3) })
    }

    // --- Tracking and selection --------------------------------------------------------

    private fun det(
        x: Double,
        label: String = "person",
    ) = Detection(Box(x, 0.4, x + 0.2, 0.6), label, 0.9)

    @Test
    fun `tracker keeps identity smooths and expires`() {
        val tracker = Tracker(config.tracking)
        val first = tracker.update(listOf(det(0.10)), 0.0).single()
        val second = tracker.update(listOf(det(0.15)), 0.1).single()
        assertEquals(first.id, second.id)
        assertEquals(0.10 + config.tracking.positionSmoothing * 0.05, second.box.x0, 1e-12)
        assertTrue(second.velocityX > 0)
        assertEquals(1, tracker.confirmed().size)
        val other = tracker.update(listOf(det(0.15, "dog")), 0.2).single()
        assertTrue(other.id != first.id)
        repeat(config.tracking.maxMissedFrames + 1) { tracker.update(emptyList(), 0.3 + it * 0.1) }
        assertTrue(tracker.tracks.isEmpty())
    }

    @Test
    fun `approach rate goes negative when an object comes closer`() {
        val tracker = Tracker(config.tracking)
        val track = tracker.update(listOf(det(0.4)), 0.0).single()
        repeat(20) { tracker.updateDistance(track, 1.0 - it * 0.05, it * 0.1) }
        assertTrue(track.distanceRate < -0.2)
    }

    private fun track(
        id: Int,
        distance: Double,
    ) = Track(id, "person", 0.9, Box(0.45, 0.4, 0.55, 0.5), 0.0).also { it.distance = distance }

    @Test
    fun `selection caps orders and stays sticky`() {
        val three = Prioritiser(config.priority, 3)
        val chosen = three.select(listOf(0.9, 0.1, 0.5, 0.3, 0.7).mapIndexed { i, d -> track(i, d) })
        assertEquals(listOf(1, 3, 2), chosen.map { it.first.id })

        val one = Prioritiser(config.priority, 1)
        val a = track(1, 0.30)
        val b = track(2, 0.35)
        assertEquals(
            1,
            one
                .select(listOf(a, b))
                .single()
                .first.id,
        )
        b.distance = 0.25
        assertEquals(
            1,
            one
                .select(listOf(a, b))
                .single()
                .first.id,
        )
        b.distance = 0.0
        assertEquals(
            2,
            one
                .select(listOf(a, b))
                .single()
                .first.id,
        )
    }

    // --- Whole pipeline ----------------------------------------------------------------

    private val engine by lazy { SoundEngine(config, 48000) }

    private fun sceneImage(): RgbImage {
        val w = 320
        val h = 240
        val pixels = IntArray(w * h) { rgb(128, 128, 128) }
        for (y in 96 until 144) {
            for (x in 32 until 96) pixels[y * w + x] = rgb(230, 30, 30)
            for (x in 224 until 288) pixels[y * w + x] = rgb(30, 30, 230)
        }
        return RgbImage(w, h, pixels)
    }

    private val detections =
        listOf(
            Detection(Box(0.1, 0.4, 0.3, 0.6), "cup", 0.9),
            Detection(Box(0.7, 0.4, 0.9, 0.6), "bottle", 0.8),
        )

    private fun nearLeftDepth(): DisparityMap {
        val values = FloatArray(320 * 240) { 1f }
        for (y in 0 until 240) for (x in 0 until 160) values[y * 320 + x] = 10f
        return DisparityMap(320, 240, values)
    }

    @Test
    fun `pipeline turns detections into sounding objects`() {
        val pipeline = FramePipeline(config, engine, LiveMixer(engine), LatencyMonitor())
        var snapshot = pipeline.processFrame(Frame(sceneImage(), 0, System.nanoTime()), detections)
        assertTrue(snapshot.objects.all { it.params == null }, "unconfirmed tracks stay silent")
        for (index in 1L..3L) {
            pipeline.submitDepth(nearLeftDepth(), index)
            snapshot = pipeline.processFrame(Frame(sceneImage(), index, System.nanoTime()), detections)
        }
        val sounding = snapshot.objects.filter { it.params != null }.associateBy { it.label }
        assertEquals(setOf("cup", "bottle"), sounding.keys)
        val cup = sounding.getValue("cup")
        val bottle = sounding.getValue("bottle")
        assertEquals(0.0, cup.soundDistance)
        assertEquals(1.0, bottle.soundDistance)
        val cupParams = assertNotNull(cup.params)
        val bottleParams = assertNotNull(bottle.params)
        assertTrue(cupParams.azimuthDeg < 0 && bottleParams.azimuthDeg > 0)
        assertTrue(cupParams.pulseHz > bottleParams.pulseHz)
        assertTrue(cupParams.levels.pluck > 0 && cupParams.levels.flute == 0.0)
        assertTrue(bottleParams.levels.flute > 0 && bottleParams.levels.pluck == 0.0)
    }

    @Test
    fun `pipeline runs without depth using a neutral distance`() {
        val pipeline = FramePipeline(config, engine, LiveMixer(engine), LatencyMonitor())
        var snapshot = pipeline.processFrame(Frame(sceneImage(), 0, System.nanoTime()), detections)
        snapshot = pipeline.processFrame(Frame(sceneImage(), 1, System.nanoTime()), detections)
        assertNull(snapshot.disparity)
        assertTrue(snapshot.objects.all { it.soundDistance == 0.5 && it.params != null })
    }
}
