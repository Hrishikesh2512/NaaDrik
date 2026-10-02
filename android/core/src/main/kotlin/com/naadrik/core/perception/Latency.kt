package com.naadrik.core.perception

const val END_TO_END = "end_to_end"

data class StageStats(
    val meanMs: Double,
    val p95Ms: Double,
    val count: Long,
)

/** Rolling latency statistics per pipeline stage; thread-safe. */
class LatencyMonitor(
    private val window: Int = 300,
) {
    private val samples = HashMap<String, ArrayDeque<Double>>()
    private val totals = HashMap<String, Long>()

    @Synchronized
    fun record(
        stage: String,
        seconds: Double,
    ) {
        val queue = samples.getOrPut(stage) { ArrayDeque() }
        queue.addLast(seconds)
        if (queue.size > window) queue.removeFirst()
        totals[stage] = (totals[stage] ?: 0L) + 1
    }

    @Synchronized
    fun summary(): Map<String, StageStats> =
        samples.filterValues { it.isNotEmpty() }.mapValues { (stage, queue) ->
            val values = queue.toDoubleArray()
            StageStats(values.average() * 1e3, percentile(values, 95.0) * 1e3, totals.getValue(stage))
        }

    fun format(): String =
        summary()
            .toSortedMap()
            .entries
            .joinToString(", ") { (stage, s) ->
                "$stage %.0f ms (p95 %.0f)".format(s.meanMs, s.p95Ms)
            }.ifEmpty { "no measurements yet" }
}
