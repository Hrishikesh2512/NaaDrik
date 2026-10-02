package com.naadrik.core.perception

import com.naadrik.core.config.ColourConfig

private const val TARGET_GREY = 0.45
private const val GAIN_MIN = 0.5
private const val GAIN_MAX = 4.0
private const val GAIN_SMOOTHING = 0.1

/**
 * Per-channel gains that bring the frame's average to mid grey: removes colour casts and
 * normalises exposure, so a dim room does not turn every object silent.
 */
fun greyWorldGains(image: RgbImage): DoubleArray {
    var r = 0.0
    var g = 0.0
    var b = 0.0
    for (p in image.pixels) {
        r += (p shr 16) and 0xFF
        g += (p shr 8) and 0xFF
        b += p and 0xFF
    }
    val n = image.pixels.size * 255.0
    return doubleArrayOf(r / n, g / n, b / n).map { (TARGET_GREY / maxOf(it, 1e-3)).coerceIn(GAIN_MIN, GAIN_MAX) }.toDoubleArray()
}

/** Median RGB of a box's centre after white balance, as in naadrik/colour.py. */
class ColourSampler(
    private val cfg: ColourConfig,
) {
    var gains = doubleArrayOf(1.0, 1.0, 1.0)
        private set
    private var hasGains = false

    fun updateWhiteBalance(image: RgbImage) {
        if (!cfg.whiteBalance) return
        val fresh = greyWorldGains(image)
        // Smooth across frames so auto-exposure flicker does not change object colours.
        gains = if (hasGains) DoubleArray(3) { gains[it] + GAIN_SMOOTHING * (fresh[it] - gains[it]) } else fresh
        hasGains = true
    }

    fun sample(
        image: RgbImage,
        box: Box,
    ): Triple<Double, Double, Double> {
        val (left, top, right, bottom) = box.central(cfg.centralFraction).pixelBounds(image.height, image.width).toList()
        val count = (right - left) * (bottom - top)
        val channels = Array(3) { DoubleArray(count) }
        var k = 0
        for (y in top until bottom) {
            for (x in left until right) {
                val p = image.pixels[y * image.width + x]
                channels[0][k] = ((p shr 16) and 0xFF).toDouble()
                channels[1][k] = ((p shr 8) and 0xFF).toDouble()
                channels[2][k] = (p and 0xFF).toDouble()
                k++
            }
        }

        fun channel(i: Int) = (median(channels[i]) / 255.0 * gains[i]).coerceIn(0.0, 1.0)
        return Triple(channel(0), channel(1), channel(2))
    }
}
