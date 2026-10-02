package com.naadrik.core.perception

import com.naadrik.core.config.DepthConfig

private const val SCENE_LOW_PERCENTILE = 5.0
private const val SCENE_HIGH_PERCENTILE = 95.0

/** Near and far reference disparities recorded by calibration. */
data class Calibration(
    val nearDisparity: Double,
    val farDisparity: Double,
) {
    init {
        require(nearDisparity > farDisparity) { "calibration near disparity must exceed far disparity" }
    }
}

/** Median disparity over the central part of the box, which is mostly the object itself. */
fun boxDisparity(
    map: DisparityMap,
    box: Box,
    fraction: Double,
): Double {
    val (left, top, right, bottom) = box.central(fraction).pixelBounds(map.height, map.width).toList()
    val values = DoubleArray((right - left) * (bottom - top))
    var k = 0
    for (y in top until bottom) for (x in left until right) values[k++] = map.values[y * map.width + x].toDouble()
    return median(values)
}

/**
 * Relative depth to normalised distance (0 near, 1 far): against the frame's own disparity
 * range ("scene") or against two calibrated references.
 */
class DistanceNormaliser(
    private val cfg: DepthConfig,
    private val calibration: Calibration? = null,
) {
    init {
        require(cfg.normalisation == "scene" || calibration != null) { "calibrated normalisation needs a calibration" }
    }

    /** Frame-wide (far, near) disparity references, computed once per depth map. */
    fun sceneRange(map: DisparityMap): Pair<Double, Double> {
        val all = DoubleArray(map.values.size) { map.values[it].toDouble() }
        return percentile(all.copyOf(), SCENE_LOW_PERCENTILE) to percentile(all, SCENE_HIGH_PERCENTILE)
    }

    fun distance(
        map: DisparityMap,
        box: Box,
        sceneRange: Pair<Double, Double>? = null,
    ): Double {
        val value = boxDisparity(map, box, cfg.boxFraction)
        val (far, near) =
            if (cfg.normalisation == "calibrated" && calibration != null) {
                calibration.farDisparity to calibration.nearDisparity
            } else {
                sceneRange ?: sceneRange(map)
            }
        if (near - far <= 1e-6) return 0.5
        val closeness = (value - far) / (near - far)
        return 1.0 - closeness.coerceIn(0.0, 1.0)
    }
}

/** Quantise into [levels] equal bins, holding the previous level within [margin] (hysteresis). */
fun quantiseDistance(
    distance: Double,
    previousLevel: Int?,
    levels: Int,
    margin: Double,
): Int {
    val level = minOf((distance * levels).toInt(), levels - 1)
    if (previousLevel == null || level == previousLevel) return level
    val lowEdge = previousLevel.toDouble() / levels - margin
    val highEdge = (previousLevel + 1).toDouble() / levels + margin
    return if (distance in lowEdge..highEdge) previousLevel else level
}

fun levelToDistance(
    level: Int,
    levels: Int,
): Double = level.toDouble() / (levels - 1)
