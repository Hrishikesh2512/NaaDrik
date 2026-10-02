package com.naadrik.core.sound

/** Listening demo: the same scenarios as `naadrik demo` in the Python prototype. */
data class Scenario(
    val name: String,
    val description: String,
    val parts: List<Part>,
    val durationS: Double = 3.0,
) {
    companion object {
        /** Everything sounds together for the whole scenario. */
        fun together(
            name: String,
            description: String,
            paths: List<(Double) -> ObjectState>,
            durationS: Double = 3.0,
        ) = Scenario(name, description, paths.map { Part(it) }, durationS)

        /**
         * A comparison: [left] alone, then [right] alone, then both. Played simultaneously from
         * the start, two sounds that differ only in loudness or timbre are hard to compare.
         */
        fun versus(
            name: String,
            description: String,
            left: (Double) -> ObjectState,
            right: (Double) -> ObjectState,
        ) = Scenario(
            name,
            description,
            listOf(
                Part(left, 0.0, VERSUS_SOLO_S),
                Part(right, VERSUS_SOLO_S + VERSUS_GAP_S, 2 * VERSUS_SOLO_S + VERSUS_GAP_S),
                Part(left, 2 * (VERSUS_SOLO_S + VERSUS_GAP_S)),
                Part(right, 2 * (VERSUS_SOLO_S + VERSUS_GAP_S)),
            ),
            3 * VERSUS_SOLO_S + 2 * VERSUS_GAP_S,
        )

        const val VERSUS_SOLO_S = 2.0
        const val VERSUS_GAP_S = 0.6
    }
}

private fun still(
    x: Double,
    y: Double,
    distance: Double,
    r: Double,
    g: Double,
    b: Double,
): (Double) -> ObjectState {
    val state = ObjectState(x, y, distance, r, g, b)
    return { _ -> state }
}

private fun moving(
    durationS: Double,
    start: ObjectState,
    end: ObjectState,
): (Double) -> ObjectState =
    { t ->
        val k = (t / durationS).coerceIn(0.0, 1.0)

        fun lerp(
            a: Double,
            b: Double,
        ) = a + (b - a) * k
        ObjectState(
            lerp(start.x, end.x),
            lerp(start.y, end.y),
            lerp(start.distance, end.distance),
            lerp(start.r, end.r),
            lerp(start.g, end.g),
            lerp(start.b, end.b),
        )
    }

val SCENARIOS: List<Scenario> =
    listOf(
        Scenario.together(
            "Red, high, left, close",
            "Fast sitar plucks, high pitch, left ear.",
            listOf(still(0.1, 0.1, 0.0, 1.0, 0.0, 0.0)),
        ),
        Scenario.together(
            "Blue, low, right, far",
            "Slow low flute notes, right ear.",
            listOf(still(0.9, 0.9, 1.0, 0.0, 0.0, 1.0)),
            4.0,
        ),
        Scenario.together(
            "Green, centre, mid",
            "Violin in the middle at a medium pulse.",
            listOf(still(0.5, 0.5, 0.5, 0.0, 1.0, 0.0)),
        ),
        Scenario.together("Yellow", "Red plus green: sitar and violin.", listOf(still(0.35, 0.4, 0.35, 1.0, 0.9, 0.1))),
        Scenario.together("Cyan", "Green plus blue: violin and flute.", listOf(still(0.65, 0.4, 0.35, 0.1, 0.9, 0.9))),
        Scenario.together("Magenta", "Red plus blue: sitar and flute.", listOf(still(0.5, 0.4, 0.35, 0.9, 0.1, 0.9))),
        Scenario.together("Orange", "Loud sitar with a quiet violin.", listOf(still(0.5, 0.4, 0.35, 1.0, 0.5, 0.0))),
        Scenario.versus(
            "Dark red versus red",
            "Quiet sitar on the left, then loud sitar on the right, then both.",
            still(0.1, 0.5, 0.4, 0.45, 0.0, 0.0),
            still(0.9, 0.5, 0.4, 1.0, 0.0, 0.0),
        ),
        Scenario.versus(
            "Grey versus white",
            "All three quiet on the left, then all three loud on the right, then both.",
            still(0.1, 0.5, 0.4, 0.45, 0.45, 0.45),
            still(0.9, 0.5, 0.4, 1.0, 1.0, 1.0),
        ),
        Scenario.versus(
            "Black versus white",
            "The soft hum alone on the left, then hum plus all three on the right, then both.",
            still(0.1, 0.5, 0.2, 0.0, 0.0, 0.0),
            still(0.9, 0.5, 0.2, 1.0, 1.0, 1.0),
        ),
        Scenario.together(
            "Black",
            "No colour instruments, only the presence hum, still pulsing and placed.",
            listOf(still(0.5, 0.5, 0.0, 0.0, 0.0, 0.0)),
            1.5,
        ),
        Scenario.together(
            "Height sweep",
            "A flute climbing from the bottom of the frame to the top.",
            listOf(moving(5.0, ObjectState(0.5, 1.0, 0.0, 0.0, 0.0, 1.0), ObjectState(0.5, 0.0, 0.0, 0.0, 0.0, 1.0))),
            5.0,
        ),
        Scenario.together(
            "Pan sweep",
            "A violin gliding from far left to far right.",
            listOf(moving(5.0, ObjectState(0.0, 0.5, 0.2, 0.0, 1.0, 0.0), ObjectState(1.0, 0.5, 0.2, 0.0, 1.0, 0.0))),
            5.0,
        ),
        Scenario.together(
            "Approach",
            "A sitar approaching: the pulse speeds up, volume stays put.",
            listOf(moving(6.0, ObjectState(0.5, 0.4, 1.0, 1.0, 0.0, 0.0), ObjectState(0.5, 0.4, 0.0, 1.0, 0.0, 0.0))),
            6.0,
        ),
        Scenario.together(
            "Three objects",
            "Red high-left close, green centre mid, blue low-right far, all at once.",
            listOf(
                still(0.15, 0.2, 0.1, 1.0, 0.0, 0.0),
                still(0.5, 0.5, 0.5, 0.0, 1.0, 0.0),
                still(0.85, 0.8, 0.9, 0.0, 0.0, 1.0),
            ),
            5.0,
        ),
    )
