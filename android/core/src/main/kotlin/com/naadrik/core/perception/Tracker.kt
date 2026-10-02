package com.naadrik.core.perception

import com.naadrik.core.config.TrackingConfig
import kotlin.math.hypot

private const val VELOCITY_SMOOTHING = 0.3

class Track(
    val id: Int,
    val label: String,
    var score: Double,
    var box: Box,
    var lastSeenS: Double,
) {
    var hits = 1
    var missed = 0
    var velocityX = 0.0 // frame widths per second
    var velocityY = 0.0
    var distance: Double? = null
    var distanceRate = 0.0 // distance units per second; negative = approaching
    var distanceLevel: Int? = null
    var colour: Triple<Double, Double, Double>? = null
    internal var distanceTimeS: Double? = null

    val speed: Double get() = hypot(velocityX, velocityY)
}

/** IoU tracker (same label only) with smoothing, as naadrik/tracker.py. Times in seconds. */
class Tracker(
    private val cfg: TrackingConfig,
) {
    private var nextId = 1
    private val active = ArrayList<Track>()

    val tracks: List<Track> get() = active.toList()

    /** Tracks seen often enough to trust and seen in the latest frame. */
    fun confirmed(): List<Track> = active.filter { it.hits >= cfg.minHits && it.missed == 0 }

    fun update(
        detections: List<Detection>,
        timeS: Double,
    ): List<Track> {
        data class Pair3(
            val iou: Double,
            val track: Int,
            val detection: Int,
        )
        val pairs =
            active
                .flatMapIndexed { ti, track ->
                    detections.mapIndexedNotNull { di, det ->
                        if (track.label == det.label) Pair3(track.box.iou(det.box), ti, di) else null
                    }
                }.sortedWith(compareByDescending<Pair3> { it.iou }.thenByDescending { it.track }.thenByDescending { it.detection })
        val usedTracks = HashSet<Int>()
        val usedDetections = HashSet<Int>()
        val matched = ArrayList<Track>()
        for (pair in pairs) {
            if (pair.iou < cfg.iouThreshold) break
            if (pair.track in usedTracks || pair.detection in usedDetections) continue
            usedTracks += pair.track
            usedDetections += pair.detection
            val track = active[pair.track]
            apply(track, detections[pair.detection], timeS)
            matched += track
        }
        active.forEachIndexed { i, track -> if (i !in usedTracks) track.missed++ }
        active.removeAll { it.missed > cfg.maxMissedFrames }
        detections.forEachIndexed { i, det ->
            if (i !in usedDetections) {
                val track = Track(nextId++, det.label, det.score, det.box, timeS)
                active += track
                matched += track
            }
        }
        return matched
    }

    fun updateDistance(
        track: Track,
        distance: Double,
        timeS: Double,
    ) {
        val previous = track.distance
        val previousTime = track.distanceTimeS
        if (previous == null || previousTime == null) {
            track.distance = distance
        } else {
            val smoothed = previous + cfg.distanceSmoothing * (distance - previous)
            track.distance = smoothed
            val dt = timeS - previousTime
            if (dt > 0) {
                val rate = (smoothed - previous) / dt
                track.distanceRate += VELOCITY_SMOOTHING * (rate - track.distanceRate)
            }
        }
        track.distanceTimeS = timeS
    }

    fun updateColour(
        track: Track,
        rgb: Triple<Double, Double, Double>,
    ) {
        val old = track.colour
        val w = cfg.colourSmoothing
        track.colour =
            if (old == null) {
                rgb
            } else {
                Triple(
                    old.first + w * (rgb.first - old.first),
                    old.second + w * (rgb.second - old.second),
                    old.third + w * (rgb.third - old.third),
                )
            }
    }

    private fun apply(
        track: Track,
        det: Detection,
        timeS: Double,
    ) {
        val oldX = track.box.centreX
        val oldY = track.box.centreY
        track.box = track.box.blend(det.box, cfg.positionSmoothing)
        val dt = timeS - track.lastSeenS
        if (dt > 0) {
            val vx = (track.box.centreX - oldX) / dt
            val vy = (track.box.centreY - oldY) / dt
            track.velocityX += VELOCITY_SMOOTHING * (vx - track.velocityX)
            track.velocityY += VELOCITY_SMOOTHING * (vy - track.velocityY)
        }
        track.score = det.score
        track.lastSeenS = timeS
        track.hits++
        track.missed = 0
    }
}
