package com.naadrik.core.perception

import kotlin.math.ceil
import kotlin.math.max
import kotlin.math.min

/** Axis-aligned box in normalised image coordinates (0..1, origin top-left). */
data class Box(
    val x0: Double,
    val y0: Double,
    val x1: Double,
    val y1: Double,
) {
    val centreX: Double get() = (x0 + x1) / 2.0
    val centreY: Double get() = (y0 + y1) / 2.0
    val width: Double get() = max(0.0, x1 - x0)
    val height: Double get() = max(0.0, y1 - y0)
    val area: Double get() = width * height

    fun iou(other: Box): Double {
        val ix = max(0.0, min(x1, other.x1) - max(x0, other.x0))
        val iy = max(0.0, min(y1, other.y1) - max(y0, other.y0))
        val inter = ix * iy
        val union = area + other.area - inter
        return if (union > 0) inter / union else 0.0
    }

    fun central(fraction: Double): Box {
        val halfW = width * fraction / 2.0
        val halfH = height * fraction / 2.0
        return Box(centreX - halfW, centreY - halfH, centreX + halfW, centreY + halfH)
    }

    /** Move [weight] of the way towards [other]. */
    fun blend(
        other: Box,
        weight: Double,
    ): Box {
        val keep = 1.0 - weight
        return Box(
            x0 * keep + other.x0 * weight,
            y0 * keep + other.y0 * weight,
            x1 * keep + other.x1 * weight,
            y1 * keep + other.y1 * weight,
        )
    }

    /** Pixel bounds [left, top, right, bottom) covering the box; never empty. */
    fun pixelBounds(
        height: Int,
        width: Int,
    ): IntArray {
        val left = (x0 * width).toInt().coerceIn(0, width - 1)
        val top = (y0 * height).toInt().coerceIn(0, height - 1)
        val right = ceil(x1 * width).toInt().coerceIn(left + 1, width)
        val bottom = ceil(y1 * height).toInt().coerceIn(top + 1, height)
        return intArrayOf(left, top, right, bottom)
    }
}

data class Detection(
    val box: Box,
    val label: String,
    val score: Double,
)

/** Packed 0xAARRGGBB pixels, row-major: the processing-size camera frame. */
class RgbImage(
    val width: Int,
    val height: Int,
    val pixels: IntArray,
) {
    init {
        require(pixels.size == width * height) { "pixel count does not match $width x $height" }
    }
}

/** Relative inverse depth (larger = nearer), row-major. */
class DisparityMap(
    val width: Int,
    val height: Int,
    val values: FloatArray,
) {
    init {
        require(values.size == width * height) { "value count does not match $width x $height" }
    }
}

/** A processed camera frame. [timestampNanos] is System.nanoTime() when it reached the app. */
class Frame(
    val image: RgbImage,
    val index: Long,
    val timestampNanos: Long,
)

/** Median with numpy's convention: mean of the two middle values for an even count. */
internal fun median(values: DoubleArray): Double {
    require(values.isNotEmpty())
    values.sort()
    val mid = values.size / 2
    return if (values.size % 2 == 1) values[mid] else (values[mid - 1] + values[mid]) / 2.0
}

/** numpy-style linear-interpolated percentile of [values] (sorted in place). */
internal fun percentile(
    values: DoubleArray,
    q: Double,
): Double {
    values.sort()
    val position = q / 100.0 * (values.size - 1)
    val lower = position.toInt()
    val upper = min(lower + 1, values.size - 1)
    return values[lower] + (values[upper] - values[lower]) * (position - lower)
}
