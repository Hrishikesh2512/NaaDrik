package com.naadrik.core.sound

import kotlin.math.abs
import kotlin.math.ln

/** Rates closer than this ratio would keep their pulses nearly locked together. */
private const val SIMILAR_RATE_RATIO = 1.25

/**
 * Starting phase for a new voice so its pulses fall in the largest gap between the pulses of
 * voices already sounding at a similar rate.
 *
 * Two sounds with the same pitch and pulse rate whose onsets coincide fuse into one phantom
 * image in the centre of the head, so two objects at the same height and distance would be
 * heard as one. Interleaving the onsets (left, right, left, right) keeps them separate.
 * With no similar voice the new one starts immediately (phase 1).
 */
fun staggeredPhase(
    pulseHz: Double,
    others: Collection<Voice>,
): Double {
    val phases =
        others
            .filter { !it.finished && abs(ln(it.pulseHz / pulseHz)) < ln(SIMILAR_RATE_RATIO) }
            .map { it.phase % 1.0 }
            .sorted()
    if (phases.isEmpty()) return 1.0
    var bestStart = phases.last()
    var bestGap = phases.first() + 1.0 - phases.last()
    for (i in 1 until phases.size) {
        val gap = phases[i] - phases[i - 1]
        if (gap > bestGap) {
            bestGap = gap
            bestStart = phases[i - 1]
        }
    }
    val middle = (bestStart + bestGap / 2.0) % 1.0
    return if (middle == 0.0) 1.0 else middle
}
