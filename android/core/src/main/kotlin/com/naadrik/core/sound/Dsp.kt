package com.naadrik.core.sound

import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.sin
import kotlin.math.sqrt
import kotlin.math.tan

/**
 * Second-order IIR section (transposed direct form II).
 *
 * The Butterworth designs match scipy's `butter(2, ...)` (bilinear transform with prewarping),
 * so timbres follow the Python engine.
 */
class Biquad(
    private val b0: Double,
    private val b1: Double,
    private val b2: Double,
    private val a1: Double,
    private val a2: Double,
) {
    private var z1 = 0.0
    private var z2 = 0.0

    fun process(x: Double): Double {
        val y = b0 * x + z1
        z1 = b1 * x - a1 * y + z2
        z2 = b2 * x - a2 * y
        return y
    }

    fun processInPlace(signal: DoubleArray) {
        for (i in signal.indices) signal[i] = process(signal[i])
    }

    companion object {
        private fun normalised(
            b0: Double,
            b1: Double,
            b2: Double,
            a0: Double,
            a1: Double,
            a2: Double,
        ) = Biquad(b0 / a0, b1 / a0, b2 / a0, a1 / a0, a2 / a0)

        fun lowpass(
            cutoffHz: Double,
            sampleRate: Int,
            q: Double = 1.0 / sqrt(2.0),
        ): Biquad {
            val w = 2.0 * PI * cutoffHz / sampleRate
            val alpha = sin(w) / (2.0 * q)
            val c = cos(w)
            return normalised((1 - c) / 2, 1 - c, (1 - c) / 2, 1 + alpha, -2 * c, 1 - alpha)
        }

        fun highpass(
            cutoffHz: Double,
            sampleRate: Int,
            q: Double = 1.0 / sqrt(2.0),
        ): Biquad {
            val w = 2.0 * PI * cutoffHz / sampleRate
            val alpha = sin(w) / (2.0 * q)
            val c = cos(w)
            return normalised((1 + c) / 2, -(1 + c), (1 + c) / 2, 1 + alpha, -2 * c, 1 - alpha)
        }

        /** Resonant peak with unity gain at the centre, like scipy's `iirpeak`. */
        fun peak(
            centreHz: Double,
            sampleRate: Int,
            q: Double,
        ): Biquad {
            val w = 2.0 * PI * centreHz / sampleRate
            val alpha = sin(w) / (2.0 * q)
            val c = cos(w)
            return normalised(alpha, 0.0, -alpha, 1 + alpha, -2 * c, 1 - alpha)
        }
    }
}

/** First-order IIR section: y = b0 x + b1 x[-1] - a1 y[-1]. */
class OnePole(
    var b0: Double,
    var b1: Double,
    var a1: Double,
) {
    private var z = 0.0

    fun process(x: Double): Double {
        val y = b0 * x + z
        z = b1 * x - a1 * y
        return y
    }

    fun setCoefficients(
        b0: Double,
        b1: Double,
        a1: Double,
    ) {
        this.b0 = b0
        this.b1 = b1
        this.a1 = a1
    }

    companion object {
        /** First-order Butterworth low-pass, as scipy's `butter(1, cutoff, fs=sr)`. */
        fun lowpass(
            cutoffHz: Double,
            sampleRate: Int,
        ): OnePole {
            val k = tan(PI * cutoffHz / sampleRate)
            return OnePole(k / (1 + k), k / (1 + k), (k - 1) / (k + 1))
        }

        /** One-pole smoother y = (1 - p) x + p y[-1], as `lfilter([1 - p], [1, -p])`. */
        fun smoother(pole: Double) = OnePole(1.0 - pole, 0.0, -pole)
    }
}

internal fun lowpass(
    signal: DoubleArray,
    cutoffHz: Double,
    sampleRate: Int,
) = Biquad.lowpass(cutoffHz, sampleRate).processInPlace(signal)

internal fun highpass(
    signal: DoubleArray,
    cutoffHz: Double,
    sampleRate: Int,
) = Biquad.highpass(cutoffHz, sampleRate).processInPlace(signal)

/** Band-pass as a second-order high-pass then low-pass (fourth order overall, like scipy). */
internal fun bandpass(
    signal: DoubleArray,
    lowHz: Double,
    highHz: Double,
    sampleRate: Int,
) {
    highpass(signal, lowHz, sampleRate)
    lowpass(signal, highHz, sampleRate)
}

internal fun DoubleArray.peakAbs(): Double {
    var peak = 0.0
    for (v in this) if (kotlin.math.abs(v) > peak) peak = kotlin.math.abs(v)
    return peak
}

internal fun DoubleArray.normalisePeak() {
    val peak = peakAbs() + 1e-12
    for (i in indices) this[i] /= peak
}
