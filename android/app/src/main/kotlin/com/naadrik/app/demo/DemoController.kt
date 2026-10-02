package com.naadrik.app.demo

import android.content.Context
import android.util.Log
import com.naadrik.app.EngineProvider
import com.naadrik.app.LOG_TAG
import com.naadrik.app.audio.AudioOutput
import com.naadrik.app.audio.DeviceAudio
import com.naadrik.app.audio.Renderer
import com.naadrik.core.sound.LiveMixer
import com.naadrik.core.sound.ObjectState
import com.naadrik.core.sound.Scenario
import com.naadrik.core.sound.SoundEngine
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.util.concurrent.ConcurrentLinkedQueue
import java.util.concurrent.atomic.AtomicInteger

data class DemoState(
    val ready: Boolean = false,
    val busy: Boolean = false,
    val status: String = "Preparing sounds…",
    val report: List<String> = emptyList(),
)

/** Runs the A1 listening demo and the on-device engine benchmark. */
class DemoController(
    private val context: Context,
    private val scope: CoroutineScope,
) {
    private val device = DeviceAudio.query(context)
    private lateinit var engine: SoundEngine
    private var job: Job? = null
    private val _state = MutableStateFlow(DemoState())
    val state: StateFlow<DemoState> = _state

    fun load() {
        scope.launch {
            engine = EngineProvider.get(context)
            val notes = "note bank built in %.0f ms (%d notes x 4 layers)".format(EngineProvider.buildMs, engine.bank.nDegrees)
            val lines = deviceReport(context, device) + notes
            lines.forEach { Log.i(LOG_TAG, "REPORT $it") }
            _state.value = DemoState(ready = true, status = "Ready. Choose a sound.", report = lines)
        }
    }

    fun play(scenario: Scenario) =
        run("Playing ${scenario.name}. ${scenario.description}") {
            val buffer = withContext(Dispatchers.Default) { engine.renderParts(scenario.parts, scenario.durationS) }
            // Advanced by the audio thread, polled by this coroutine.
            val position = AtomicInteger(0)
            val output =
                AudioOutput(device) { frames, out ->
                    val from = position.get()
                    val count = minOf(frames * 2, buffer.size - from).coerceAtLeast(0)
                    buffer.copyInto(out, 0, from, from + count)
                    out.fill(0f, count, frames * 2)
                    position.addAndGet(count)
                }
            output.start()
            try {
                while (isActive && position.get() < buffer.size) delay(20)
                delay(150)
            } finally {
                output.stop()
            }
            "Finished ${scenario.name}."
        }

    /**
     * Ten seconds of the real-time path with three moving objects updated at camera rate, as
     * in live mode. Reports render cost against the block budget, underruns and latency.
     */
    fun benchmark() =
        run("Engine test: three moving sounds for ten seconds. Keep headphones on.") {
            val applyLatencies = ConcurrentLinkedQueue<Long>()
            val mixer = LiveMixer(engine) { captured -> applyLatencies += System.nanoTime() - captured }
            val output = AudioOutput(device, Renderer(mixer::render))
            val outputLatencies = mutableListOf<Double>()
            output.stats.reset()
            output.start()
            val start = System.nanoTime()
            try {
                while (isActive) {
                    val t = (System.nanoTime() - start) / 1e9
                    if (t >= BENCHMARK_S) break
                    mixer.update(benchmarkScene(t), System.nanoTime())
                    output.outputLatencyS()?.let { outputLatencies += it }
                    delay(UPDATE_PERIOD_MS)
                }
            } finally {
                output.stop()
            }
            val render = output.stats.summary()
            val applyMs = applyLatencies.map { it / 1e6 }.sorted()
            val outMs = outputLatencies.map { it * 1000 }.sorted()
            val lines =
                listOf(
                    "benchmark render per block: mean %.3f ms, p95 %.3f ms, max %.3f ms, budget %.2f ms (%d blocks)"
                        .format(render.meanMs, render.p95Ms, render.maxMs, render.budgetMs, render.blocks),
                    "benchmark underruns ${output.stats.underruns}, final buffer ${output.bufferFrames} frames " +
                        "(%.1f ms), fast path ${output.fastPath}".format(output.bufferFrames * 1000.0 / device.sampleRate),
                    "benchmark update->audio thread: median %.1f ms, p95 %.1f ms".format(applyMs.median(), applyMs.p95()),
                    "benchmark audio thread->DAC: median %.1f ms, p95 %.1f ms".format(outMs.median(), outMs.p95()),
                )
            lines.forEach { Log.i(LOG_TAG, "REPORT $it") }
            _state.value = _state.value.copy(report = _state.value.report + lines)
            "Engine test finished. ${output.stats.underruns} glitches."
        }

    fun stop() {
        job?.cancel()
    }

    private fun run(
        status: String,
        block: suspend CoroutineScope.() -> String,
    ) {
        if (!_state.value.ready || _state.value.busy) return
        _state.value = _state.value.copy(busy = true, status = status)
        job =
            scope.launch {
                val result =
                    try {
                        block()
                    } catch (e: Exception) {
                        Log.e(LOG_TAG, "demo failed", e)
                        "Audio error: ${e.message}"
                    }
                _state.value = _state.value.copy(busy = false, status = result)
            }
        job?.invokeOnCompletion { if (it != null) _state.value = _state.value.copy(busy = false, status = "Stopped.") }
    }

    private companion object {
        const val BENCHMARK_S = 10.0
        const val UPDATE_PERIOD_MS = 33L

        fun benchmarkScene(t: Double): Map<Int, ObjectState> {
            val sweep = (t / BENCHMARK_S).coerceIn(0.0, 1.0)
            return mapOf(
                1 to ObjectState(sweep, 0.3, 0.2, 1.0, 1.0, 1.0),
                2 to ObjectState(0.5, 0.6, 1.0 - sweep, 0.0, 0.0, 0.0),
                3 to ObjectState(1.0 - sweep, 0.8, 0.6, 0.0, 1.0, 0.0),
            )
        }

        fun List<Double>.median() = if (isEmpty()) Double.NaN else this[size / 2]

        fun List<Double>.p95() = if (isEmpty()) Double.NaN else this[(size * 95 / 100).coerceAtMost(size - 1)]
    }
}
