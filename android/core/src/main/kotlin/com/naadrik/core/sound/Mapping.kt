package com.naadrik.core.sound

import com.naadrik.core.config.ColourConfig
import com.naadrik.core.config.Config
import com.naadrik.core.config.PitchConfig
import com.naadrik.core.config.PulseConfig
import com.naadrik.core.config.SpatialConfig
import kotlin.math.ceil
import kotlin.math.pow

/** An object as the sound engine sees it. All values are normalised to [0, 1]. */
data class ObjectState(
    val x: Double,
    val y: Double,
    val distance: Double,
    val r: Double,
    val g: Double,
    val b: Double,
)

/** Gains for (pluck, bowed, flute). */
data class Levels(
    val pluck: Double,
    val bowed: Double,
    val flute: Double,
) {
    operator fun get(index: Int): Double =
        when (index) {
            0 -> pluck
            1 -> bowed
            2 -> flute
            else -> throw IndexOutOfBoundsException(index)
        }
}

data class SoundParams(
    val azimuthDeg: Double,
    val degree: Int,
    val pulseHz: Double,
    val levels: Levels,
)

internal fun clamp01(value: Double): Double = value.coerceIn(0.0, 1.0)

fun scaleFrequencies(cfg: PitchConfig): DoubleArray {
    val span = cfg.octaves * 12.0
    val semitones =
        (0..ceil(cfg.octaves).toInt()).flatMap { octave ->
            cfg.scale.map { octave * 12 + it }.filter { it <= span + 1e-9 }
        }
    return semitones.map { cfg.baseHz * 2.0.pow(it / 12.0) }.toDoubleArray()
}

/** Vertical position (0 = top) to scale degree (0 = lowest). Rounds half to even like Python. */
fun heightToDegree(
    y: Double,
    nDegrees: Int,
): Int = Math.rint((1.0 - clamp01(y)) * (nDegrees - 1)).toInt()

/** Log-interpolated so each step in distance feels even. */
fun distanceToPulseRate(
    distance: Double,
    cfg: PulseConfig,
): Double = cfg.nearHz * (cfg.farHz / cfg.nearHz).pow(clamp01(distance))

/** 0 (off), 1 (low) or 2 (high). */
fun quantiseChannel(
    value: Double,
    cfg: ColourConfig,
): Int {
    val v = clamp01(value)
    return when {
        v < cfg.thresholds[0] -> 0
        v < cfg.thresholds[1] -> 1
        else -> 2
    }
}

fun rgbToLevels(
    r: Double,
    g: Double,
    b: Double,
    cfg: ColourConfig,
): Levels =
    Levels(
        cfg.levels[quantiseChannel(r, cfg)],
        cfg.levels[quantiseChannel(g, cfg)],
        cfg.levels[quantiseChannel(b, cfg)],
    )

/** Horizontal position (0 = left edge) to azimuth in degrees, negative = left. */
fun xToAzimuth(
    x: Double,
    cfg: SpatialConfig,
): Double = (clamp01(x) - 0.5) * 2.0 * cfg.maxAzimuthDeg

fun mapObject(
    config: Config,
    nDegrees: Int,
    obj: ObjectState,
): SoundParams =
    SoundParams(
        azimuthDeg = xToAzimuth(obj.x, config.spatial),
        degree = heightToDegree(obj.y, nDegrees),
        pulseHz = distanceToPulseRate(obj.distance, config.pulse),
        levels = rgbToLevels(obj.r, obj.g, obj.b, config.colour),
    )
