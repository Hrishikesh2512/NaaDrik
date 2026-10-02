package com.naadrik.core.perception

import com.naadrik.core.config.PriorityConfig
import kotlin.math.abs

private const val UNKNOWN_DISTANCE = 0.5

fun motionFactor(
    track: Track,
    cfg: PriorityConfig,
): Double {
    val approaching = -track.distanceRate >= cfg.approachSpeed
    val moving = track.speed >= cfg.movingSpeed
    return if (approaching || moving) 1.0 + cfg.motionBoost else 1.0
}

/** closeness x class importance x centredness, boosted for motion. */
fun priorityScore(
    track: Track,
    cfg: PriorityConfig,
): Double {
    val closeness = 1.0 - (track.distance ?: UNKNOWN_DISTANCE).coerceIn(0.0, 1.0)
    val importance = cfg.classImportance[track.label] ?: cfg.defaultImportance
    val offset = minOf(1.0, 2.0 * abs(track.box.centreX - 0.5))
    val centredness = 1.0 - cfg.centreWeight * offset
    return closeness * importance * centredness * motionFactor(track, cfg)
}

/** Keeps the selection stable: a sounding object is only replaced by a clearly better one. */
class Prioritiser(
    private val cfg: PriorityConfig,
    private val maxObjects: Int,
) {
    private var selected: List<Int> = emptyList()

    fun select(tracks: List<Track>): List<Pair<Track, Double>> {
        val scored = tracks.associate { it.id to (it to priorityScore(it, cfg)) }

        fun score(id: Int) = scored.getValue(id).second
        val kept = selected.filter { it in scored }.toMutableList()
        val candidates =
            scored.keys
                .filter { it !in kept }
                .sortedByDescending(::score)
                .toMutableList()
        while (kept.size < maxObjects && candidates.isNotEmpty()) kept += candidates.removeAt(0)
        while (candidates.isNotEmpty() && kept.isNotEmpty()) {
            val weakest = kept.minBy(::score)
            if (score(candidates[0]) <= score(weakest) + cfg.switchMargin) break
            kept[kept.indexOf(weakest)] = candidates.removeAt(0)
            candidates += weakest
            candidates.sortByDescending(::score)
        }
        kept.sortByDescending(::score)
        selected = kept.toList()
        return kept.map { scored.getValue(it) }
    }
}
