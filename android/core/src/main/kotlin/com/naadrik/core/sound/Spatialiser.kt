package com.naadrik.core.sound

import com.naadrik.core.config.SpatialConfig
import kotlin.math.PI
import kotlin.math.abs
import kotlin.math.ceil
import kotlin.math.cos
import kotlin.math.floor
import kotlin.math.hypot
import kotlin.math.max
import kotlin.math.pow
import kotlin.math.sin
import kotlin.math.sqrt

/*
 * Streaming binaural spatialiser for one mono source: a port of naadrik/spatialiser.py.
 *
 * head_model: Woodworth ITD plus a power-normalised Brown-Duda head-shadow filter per ear.
 * pan: the same ITD with constant-power level panning. Azimuth: 0 ahead, positive right.
 */

const val SPEED_OF_SOUND_M_S = 343.0
private const val ALPHA_MIN = 0.1
private const val THETA_MIN_DEG = 150.0

fun wrapDegrees(angle: Double): Double = ((angle + 180.0) % 360.0 + 360.0) % 360.0 - 180.0

/** Rear azimuths fold onto the front: ITD and ILD depend only on the lateral angle. */
fun lateralAngle(azimuthDeg: Double): Double {
    var azimuth = wrapDegrees(azimuthDeg)
    if (azimuth > 90.0) {
        azimuth = 180.0 - azimuth
    } else if (azimuth < -90.0) {
        azimuth = -180.0 - azimuth
    }
    return Math.toRadians(azimuth)
}

/** Seconds; positive when the source is on the right (left ear lags). */
fun interauralTimeDifference(
    azimuthDeg: Double,
    headRadiusM: Double,
): Double {
    val lateral = lateralAngle(azimuthDeg)
    return headRadiusM / SPEED_OF_SOUND_M_S * (lateral + sin(lateral))
}

fun shadowAlpha(angleFromEarDeg: Double): Double {
    val theta = abs(wrapDegrees(angleFromEarDeg))
    return (1.0 + ALPHA_MIN / 2.0) + (1.0 - ALPHA_MIN / 2.0) * cos(Math.toRadians(theta / THETA_MIN_DEG * 180.0))
}

/** High-frequency gains (left, right), power-normalised so position never changes loudness. */
fun earAlphas(azimuthDeg: Double): Pair<Double, Double> {
    val left = shadowAlpha(azimuthDeg + 90.0)
    val right = shadowAlpha(azimuthDeg - 90.0)
    val front = sqrt(2.0) * shadowAlpha(90.0)
    val scale = front / hypot(left, right)
    return left * scale to right * scale
}

/** Head shadow (2w0 + alpha s) / (2w0 + s) by bilinear transform: (b0, b1, a1). */
fun headShadowCoefficients(
    alpha: Double,
    headRadiusM: Double,
    sr: Int,
): DoubleArray {
    val w0 = SPEED_OF_SOUND_M_S / headRadiusM
    val k = 2.0 * sr
    val norm = 2.0 * w0 + k
    return doubleArrayOf((2.0 * w0 + alpha * k) / norm, (2.0 * w0 - alpha * k) / norm, (2.0 * w0 - k) / norm)
}

class Spatialiser(
    private val cfg: SpatialConfig,
    private val sr: Int,
    maxBlock: Int,
) {
    private val historyLength = ceil(cfg.headRadiusM / SPEED_OF_SOUND_M_S * (PI / 2 + 1.0) * sr).toInt() + 2
    private val buffer = DoubleArray(historyLength + maxBlock)
    private var azimuth = Double.NaN
    private val delays = DoubleArray(2)
    private val gains = DoubleArray(2)
    private val targetDelays = DoubleArray(2)
    private val targetGains = DoubleArray(2)
    private val shadow = arrayOf(OnePole(1.0, 0.0, 0.0), OnePole(1.0, 0.0, 0.0))
    private val rear = OnePole.lowpass(cfg.rearLowpassHz, sr)

    /**
     * Add one block of [mono] (first [n] samples) to interleaved stereo [out], gliding from the
     * previous azimuth to [azimuthDeg].
     */
    fun process(
        mono: DoubleArray,
        n: Int,
        azimuthDeg: Double,
        out: FloatArray,
    ) {
        computeTargets(azimuthDeg)
        if (azimuth.isNaN()) {
            targetDelays.copyInto(delays)
            targetGains.copyInto(gains)
        }
        azimuth = azimuthDeg

        // Always run the rear filter so its state is warm when a source swings behind the head.
        val behind = max(0.0, abs(wrapDegrees(azimuthDeg)) - 90.0) / 90.0
        for (i in 0 until n) {
            val dark = rear.process(mono[i])
            buffer[historyLength + i] = if (behind == 0.0) mono[i] else (1.0 - behind) * mono[i] + behind * dark
        }
        if (cfg.mode == "head_model") {
            val (alphaLeft, alphaRight) = earAlphas(azimuthDeg)
            setShadow(0, alphaLeft)
            setShadow(1, alphaRight)
        }
        for (ear in 0..1) {
            for (i in 0 until n) {
                val ramp = (i + 1).toDouble() / n
                val delay = delays[ear] + (targetDelays[ear] - delays[ear]) * ramp
                val position = historyLength + i - delay
                val base = floor(position).toInt()
                val frac = position - base
                var sample = buffer[base] + (buffer[minOf(base + 1, historyLength + n - 1)] - buffer[base]) * frac
                if (cfg.mode == "head_model") sample = shadow[ear].process(sample)
                val gain = gains[ear] + (targetGains[ear] - gains[ear]) * ramp
                out[2 * i + ear] += (sample * gain).toFloat()
            }
        }
        System.arraycopy(buffer, n, buffer, 0, historyLength)
        targetDelays.copyInto(delays)
        targetGains.copyInto(gains)
    }

    private fun setShadow(
        ear: Int,
        alpha: Double,
    ) {
        val c = headShadowCoefficients(alpha, cfg.headRadiusM, sr)
        shadow[ear].setCoefficients(c[0], c[1], c[2])
    }

    private fun computeTargets(azimuthDeg: Double) {
        val itd = interauralTimeDifference(azimuthDeg, cfg.headRadiusM) * sr
        targetDelays[0] = max(itd, 0.0)
        targetDelays[1] = max(-itd, 0.0)
        val side = sin(lateralAngle(azimuthDeg))
        if (cfg.mode == "pan") {
            val angle = (side + 1.0) * PI / 4.0
            targetGains[0] = cos(angle) * sqrt(2.0)
            targetGains[1] = sin(angle) * sqrt(2.0)
        } else {
            val far = 10.0.pow(-cfg.extraIldDb * abs(side) / 20.0)
            targetGains[0] = if (side > 0) far else 1.0
            targetGains[1] = if (side > 0) 1.0 else far
        }
    }
}
