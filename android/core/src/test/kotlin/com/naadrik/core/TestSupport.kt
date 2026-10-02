package com.naadrik.core

import com.naadrik.core.config.Config
import java.io.File
import kotlin.math.ln
import kotlin.math.sqrt

object TestSupport {
    val repoRoot = File(System.getProperty("naadrik.repoRoot") ?: "../..")
    val configText: String by lazy { File(repoRoot, "config.yaml").readText() }
    val config: Config by lazy { Config.parse(configText) }
}

/** Autocorrelation pitch with parabolic peak refinement (same method as the Python tests). */
fun estimateF0(
    x: DoubleArray,
    sr: Int,
    fmin: Double = 80.0,
    fmax: Double = 2000.0,
): Double {
    val mean = x.average()
    val centred = DoubleArray(x.size) { x[it] - mean }
    val lo = (sr / fmax).toInt()
    val hi = (sr / fmin).toInt()
    val corr = DoubleArray(hi + 2)
    for (lag in lo - 1..hi + 1) {
        var sum = 0.0
        for (i in 0 until centred.size - lag) sum += centred[i] * centred[i + lag]
        corr[lag] = sum
    }
    var best = lo
    for (lag in lo..hi) if (corr[lag] > corr[best]) best = lag
    val a = corr[best - 1]
    val b = corr[best]
    val c = corr[best + 1]
    return sr / (best + 0.5 * (a - c) / (a - 2 * b + c))
}

fun cents(
    f: Double,
    ref: Double,
) = 1200 * ln(f / ref) / ln(2.0)

/** RMS of (left, right) over interleaved stereo. */
fun channelRms(stereo: FloatArray): Pair<Double, Double> {
    var l = 0.0
    var r = 0.0
    val frames = stereo.size / 2
    for (i in 0 until frames) {
        l += stereo[2 * i] * stereo[2 * i].toDouble()
        r += stereo[2 * i + 1] * stereo[2 * i + 1].toDouble()
    }
    return sqrt(l / frames) to sqrt(r / frames)
}

fun mono(stereo: FloatArray) = DoubleArray(stereo.size / 2) { (stereo[2 * it] + stereo[2 * it + 1]).toDouble() }

/** Notes that start after at least [minGapS] of silence (mirrors the Python helper). */
fun countPulses(
    stereo: FloatArray,
    sr: Int,
    minGapS: Double = 0.02,
): Int {
    val gap = (minGapS * sr).toInt()
    var lastActive = -gap - 1
    var count = 0
    for (i in 0 until stereo.size / 2) {
        val active = kotlin.math.abs(stereo[2 * i]) + kotlin.math.abs(stereo[2 * i + 1]) > 1e-4
        if (active) {
            if (i - lastActive > gap) count++
            lastActive = i
        }
    }
    return count
}
