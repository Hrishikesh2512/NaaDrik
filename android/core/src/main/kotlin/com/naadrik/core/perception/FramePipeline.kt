package com.naadrik.core.perception

import com.naadrik.core.config.Config
import com.naadrik.core.sound.LiveMixer
import com.naadrik.core.sound.ObjectState
import com.naadrik.core.sound.SoundEngine
import com.naadrik.core.sound.SoundParams

private const val UNKNOWN_DISTANCE = 0.5
private val NEUTRAL_COLOUR = Triple(0.5, 0.5, 0.5)

/** What the debug view and accessibility summary show for one tracked object. */
data class ObjectView(
    val trackId: Int,
    val label: String,
    val score: Double,
    val box: Box,
    val distance: Double?,
    val soundDistance: Double,
    val colour: Triple<Double, Double, Double>,
    val priority: Double,
    val params: SoundParams?, // null when tracked but not sounding
)

class Snapshot(
    val frame: Frame,
    val objects: List<ObjectView>,
    val disparity: DisparityMap?,
)

/**
 * Per-frame logic of the live pipeline, a port of naadrik/pipeline.py. Model inference runs in
 * the app; this turns detections and the latest depth map into tracked, prioritised voices.
 * [processFrame] runs on one thread; [submitDepth] may be called from another.
 */
class FramePipeline(
    private val config: Config,
    private val engine: SoundEngine,
    private val mixer: LiveMixer,
    private val monitor: LatencyMonitor,
    private val normaliser: DistanceNormaliser = DistanceNormaliser(config.depth),
) {
    private val tracker = Tracker(config.tracking)
    private val prioritiser = Prioritiser(config.priority, config.objects.maxObjects)
    private val colour = ColourSampler(config.colour)

    @Volatile private var latestDepth: Pair<DisparityMap, Long>? = null
    private var depthUsed = -1L
    private var sceneRange: Pair<Double, Double>? = null

    @Volatile var snapshot: Snapshot? = null
        private set

    fun submitDepth(
        map: DisparityMap,
        frameIndex: Long,
    ) {
        latestDepth = map to frameIndex
    }

    fun processFrame(
        frame: Frame,
        detections: List<Detection>,
    ): Snapshot {
        val timeS = frame.timestampNanos / 1e9
        colour.updateWhiteBalance(frame.image)
        val matched = tracker.update(detections, timeS)
        val disparity = updateDistances(matched, timeS)
        for (track in matched) tracker.updateColour(track, colour.sample(frame.image, track.box))

        val selected = prioritiser.select(tracker.confirmed())
        val states = selected.associate { (track, _) -> track.id to objectState(track) }
        mixer.update(states, frame.timestampNanos)
        monitor.record("pipeline", (System.nanoTime() - frame.timestampNanos) / 1e9)

        val scores = selected.associate { (track, score) -> track.id to score }
        val views =
            tracker.tracks
                .filter { it.missed == 0 }
                .map { track ->
                    ObjectView(
                        track.id,
                        track.label,
                        track.score,
                        track.box,
                        track.distance,
                        soundDistance(track),
                        track.colour ?: NEUTRAL_COLOUR,
                        scores[track.id] ?: 0.0,
                        states[track.id]?.let(engine::map),
                    )
                }.sortedWith(compareBy<ObjectView> { it.params == null }.thenByDescending { it.priority })
        return Snapshot(frame, views, disparity).also { snapshot = it }
    }

    private fun updateDistances(
        matched: List<Track>,
        timeS: Double,
    ): DisparityMap? {
        val (map, index) = latestDepth ?: return null
        val freshMap = index != depthUsed
        if (freshMap) {
            depthUsed = index
            sceneRange = if (config.depth.normalisation == "scene") normaliser.sceneRange(map) else null
        }
        val levels = config.depth.levels
        for (track in matched) {
            // Feed a distance only when the map is new (or the track has none), so the approach
            // rate reflects real change rather than the same map read repeatedly.
            if (freshMap || track.distance == null) {
                tracker.updateDistance(track, normaliser.distance(map, track.box, sceneRange), timeS)
            }
            val distance = track.distance
            if (levels > 0 && distance != null) {
                track.distanceLevel = quantiseDistance(distance, track.distanceLevel, levels, config.depth.hysteresis)
            }
        }
        return map
    }

    private fun soundDistance(track: Track): Double {
        val levels = config.depth.levels
        val level = track.distanceLevel
        if (levels > 0 && level != null) return levelToDistance(level, levels)
        return track.distance ?: UNKNOWN_DISTANCE
    }

    private fun objectState(track: Track): ObjectState {
        val (r, g, b) = track.colour ?: NEUTRAL_COLOUR
        return ObjectState(track.box.centreX, track.box.centreY, soundDistance(track), r, g, b)
    }
}
