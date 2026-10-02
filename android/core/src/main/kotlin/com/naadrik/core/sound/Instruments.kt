package com.naadrik.core.sound

import com.naadrik.core.config.BowedConfig
import com.naadrik.core.config.FluteConfig
import com.naadrik.core.config.PluckConfig
import com.naadrik.core.config.PresenceConfig
import java.util.Random
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.exp
import kotlin.math.max
import kotlin.math.min
import kotlin.math.pow
import kotlin.math.sin
import kotlin.math.tanh

/*
 * Synthesised instruments, one per colour channel plus the presence hum. A direct port of
 * naadrik/sound_engine/instruments.py; each function renders one mono note.
 */

private const val BUZZ_THRESHOLD = 0.25
private const val END_FADE_S = 0.01

/** Sitar-like plucked string: Karplus-Strong with a bridge buzz and a sympathetic string. */
fun pluckNote(
    freq: Double,
    sr: Int,
    durationS: Double,
    cfg: PluckConfig,
    rng: Random,
): DoubleArray {
    val n = (durationS * sr).toInt()
    val string = karplusStrong(pluckExcitation(freq, sr, cfg.brightness, rng), freq, sr, cfg.decayS, n)
    string.normalisePeak()
    // A sitar's curved jawari bridge flattens one side of the string's swing; clipping one
    // polarity reproduces the bright, decaying buzz as the amplitude drops below the contact.
    val buzzed = DoubleArray(n) { string[it] - cfg.buzz * max(string[it] - BUZZ_THRESHOLD, 0.0) }
    val sympathetic = karplusStrong(DoubleArray(n) { buzzed[it] * 0.05 }, 2.0 * freq, sr, cfg.decayS * 2.0, n)
    sympathetic.normalisePeak()
    val out = DoubleArray(n) { buzzed[it] + cfg.sympathetic * sympathetic[it] }
    if (cfg.drive > 0.0) {
        val norm = tanh(cfg.drive)
        for (i in out.indices) out[i] = tanh(cfg.drive * out[i]) / norm
    }
    return finish(out, sr)
}

/** Violin-like bowed string: band-limited sawtooth with delayed vibrato and body resonances. */
fun bowedNote(
    freq: Double,
    sr: Int,
    durationS: Double,
    cfg: BowedConfig,
    rng: Random,
): DoubleArray {
    val n = (durationS * sr).toInt()
    val phase =
        vibratoPhase(freq, n, sr, cfg.vibratoHz) { t ->
            cfg.vibratoCents * ((t - cfg.vibratoDelayS) / 0.15).coerceIn(0.0, 1.0)
        }
    val harmonics = max(1, (min(cfg.cutoffHz, 0.45 * sr) / freq).toInt())
    val saw = DoubleArray(n)
    for (i in 0 until n) saw[i] = harmonicSum(phase[i], harmonics) { k -> 1.0 / k }
    val body = saw.copyOf()
    for (resonance in cfg.bodyResonancesHz) {
        if (resonance < 0.45 * sr) {
            val filter = Biquad.peak(resonance, sr, 4.0)
            for (i in 0 until n) body[i] += 0.6 * filter.process(saw[i])
        }
    }
    body.normalisePeak()
    val noise = DoubleArray(n) { rng.nextGaussian() }
    lowpass(noise, 3000.0, sr)
    val out = DoubleArray(n) { (body[it] + noise[it] * cfg.bowNoise) * (it.toDouble() / sr / 0.03).coerceAtMost(1.0) }
    return finish(out, sr)
}

/** Flute: few sine partials, breath noise, an onset chiff and gentle vibrato. */
fun fluteNote(
    freq: Double,
    sr: Int,
    durationS: Double,
    cfg: FluteConfig,
    rng: Random,
): DoubleArray {
    val n = (durationS * sr).toInt()
    val phase = vibratoPhase(freq, n, sr, cfg.vibratoHz) { cfg.vibratoCents }
    val tone = DoubleArray(n) { i -> cfg.harmonics.indices.sumOf { k -> cfg.harmonics[k] * sin((k + 1) * phase[i]) } }
    tone.normalisePeak()
    val breath = DoubleArray(n) { rng.nextGaussian() }
    bandpass(breath, freq * 0.8, min(freq * 6.0, 0.45 * sr), sr)
    breath.normalisePeak()
    val chiff = DoubleArray(n) { rng.nextGaussian() }
    highpass(chiff, 1500.0, sr)
    for (i in 0 until n) chiff[i] *= exp(-i.toDouble() / sr / 0.025)
    chiff.normalisePeak()
    val out =
        DoubleArray(n) { i ->
            val t = i.toDouble() / sr
            val tremolo = 1.0 + cfg.tremoloDepth * sin(2 * PI * cfg.vibratoHz * t)
            val attack = (t / 0.04).coerceAtMost(1.0)
            (tone[i] + cfg.breath * breath[i]) * tremolo * attack + cfg.chiff * chiff[i]
        }
    return finish(out, sr)
}

/**
 * Neutral presence hum: a muted triangle at the note's pitch plus soft pitched noise.
 *
 * It carries pitch, pulse and position for objects with no colour energy. It is deliberately
 * plain (no vibrato, attack transient or breath) so it never reads as a colour instrument.
 */
fun presenceNote(
    freq: Double,
    sr: Int,
    durationS: Double,
    cfg: PresenceConfig,
    rng: Random,
): DoubleArray {
    val n = (durationS * sr).toInt()
    val cutoff = min(cfg.cutoffRatio * freq, 0.45 * sr)
    val hum = DoubleArray(n)
    val top = (cutoff / freq).toInt()
    for (i in 0 until n) {
        val t = i.toDouble() / sr
        var sum = 0.0
        var k = 1
        while (k <= top) {
            val sign = if (((k - 1) / 2) % 2 == 0) 1.0 else -1.0
            sum += sign * sin(2 * PI * k * freq * t) / (k * k)
            k += 2
        }
        hum[i] = sum
    }
    lowpass(hum, cutoff, sr)
    hum.normalisePeak()
    val noise = DoubleArray(n) { rng.nextGaussian() }
    bandpass(noise, freq * 0.7, min(freq * 1.5, 0.45 * sr), sr)
    noise.normalisePeak()
    val out =
        DoubleArray(n) { i ->
            ((1.0 - cfg.noise) * hum[i] + cfg.noise * noise[i]) * (i.toDouble() / sr / 0.02).coerceAtMost(1.0)
        }
    return finish(out, sr)
}

private fun pluckExcitation(
    freq: Double,
    sr: Int,
    brightness: Double,
    rng: Random,
): DoubleArray {
    val length = max(2, (sr / freq).toInt())
    val pole = 0.95 - 0.85 * brightness.coerceIn(0.0, 1.0)
    val smoother = OnePole.smoother(pole)
    val burst = DoubleArray(length) { smoother.process(rng.nextDouble() * 2.0 - 1.0) }
    val mean = burst.average()
    for (i in burst.indices) burst[i] -= mean
    return burst
}

/**
 * Karplus-Strong. The two-point average adds half a sample of delay; the remaining fractional
 * delay is folded into the same taps by linear interpolation, keeping every note in tune.
 */
internal fun karplusStrong(
    excitation: DoubleArray,
    freq: Double,
    sr: Int,
    decayS: Double,
    n: Int,
): DoubleArray {
    val delay = sr / freq - 0.5
    val whole = delay.toInt()
    val frac = delay - whole
    val gain = 10.0.pow(-3.0 / (decayS * freq))
    val t0 = gain * 0.5 * (1.0 - frac)
    val t1 = gain * 0.5
    val t2 = gain * 0.5 * frac
    val y = DoubleArray(n)
    for (i in 0 until n) {
        var v = if (i < excitation.size) excitation[i] else 0.0
        if (i >= whole) v += t0 * y[i - whole]
        if (i >= whole + 1) v += t1 * y[i - whole - 1]
        if (i >= whole + 2) v += t2 * y[i - whole - 2]
        y[i] = v
    }
    return y
}

private inline fun vibratoPhase(
    freq: Double,
    n: Int,
    sr: Int,
    rateHz: Double,
    depthCents: (Double) -> Double,
): DoubleArray {
    val phase = DoubleArray(n)
    var acc = 0.0
    for (i in 0 until n) {
        val t = i.toDouble() / sr
        acc += freq * 2.0.pow(depthCents(t) / 1200.0 * sin(2 * PI * rateHz * t))
        phase[i] = 2 * PI * acc / sr
    }
    return phase
}

/** sum_k weight(k) sin(k theta) via the Chebyshev recurrence: one sin/cos per sample, not per harmonic. */
private inline fun harmonicSum(
    theta: Double,
    harmonics: Int,
    weight: (Int) -> Double,
): Double {
    val s1 = sin(theta)
    val twoCos = 2.0 * cos(theta)
    var previous = 0.0
    var current = s1
    var sum = weight(1) * s1
    for (k in 2..harmonics) {
        val next = twoCos * current - previous
        previous = current
        current = next
        sum += weight(k) * current
    }
    return sum
}

private fun finish(
    note: DoubleArray,
    sr: Int,
): DoubleArray {
    val fade = (END_FADE_S * sr).toInt()
    for (j in 0 until fade) {
        val i = note.size - fade + j
        note[i] *= 1.0 - j.toDouble() / (fade - 1)
    }
    return note
}
