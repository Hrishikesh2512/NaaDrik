package com.naadrik.app.live

import android.content.Context
import android.util.Log
import androidx.camera.core.Preview
import androidx.lifecycle.LifecycleOwner
import com.naadrik.app.EngineProvider
import com.naadrik.app.LOG_TAG
import com.naadrik.app.audio.AudioOutput
import com.naadrik.app.audio.DeviceAudio
import com.naadrik.app.camera.CameraFrame
import com.naadrik.app.camera.CameraFrames
import com.naadrik.app.depth.MidasDepth
import com.naadrik.app.depth.probeArCoreDepth
import com.naadrik.app.detection.MediaPipeDetector
import com.naadrik.core.perception.END_TO_END
import com.naadrik.core.perception.Frame
import com.naadrik.core.perception.FramePipeline
import com.naadrik.core.perception.LatencyMonitor
import com.naadrik.core.perception.ObjectView
import com.naadrik.core.perception.RgbImage
import com.naadrik.core.sound.LiveMixer
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
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean

data class LiveState(
    val running: Boolean = false,
    val starting: Boolean = false,
    val status: String = "Press Start to begin sensing.",
    val objects: List<ObjectView> = emptyList(),
    val latency: String = "",
    val report: List<String> = emptyList(),
)

/**
 * Live mode: camera -> detection (+ depth every Nth frame) -> tracking -> prioritisation -> sound.
 *
 * Threads: CameraX analysis thread (detection and per-frame logic), a depth thread, and the
 * audio thread. Depth only runs when its thread is idle, so frames are dropped, never queued.
 */
class LiveController(
    private val context: Context,
    private val scope: CoroutineScope,
) {
    private val device = DeviceAudio.query(context)
    private val _state = MutableStateFlow(LiveState())
    val state: StateFlow<LiveState> = _state

    private var session: Session? = null

    private inner class Session(
        val engine: SoundEngine,
    ) {
        val config = engine.config
        val monitor = LatencyMonitor()
        val camera = CameraFrames(context, config)
        val depthExecutor: ExecutorService = Executors.newSingleThreadExecutor { Thread(it, "naadrik-depth") }
        val depthBusy = AtomicBoolean(false)
        val stopping = AtomicBoolean(false)
        lateinit var audio: AudioOutput
        val mixer =
            LiveMixer(engine) { captured ->
                monitor.record(END_TO_END, (System.nanoTime() - captured) / 1e9 + audio.latestOutputLatencyS)
            }
        val pipeline = FramePipeline(config, engine, mixer, monitor)
        lateinit var detector: MediaPipeDetector
        var depth: MidasDepth? = null
        var frameIndex = 0L
        var lastPublishNanos = 0L
        var reporter: Job? = null
    }

    fun start(
        owner: LifecycleOwner,
        preview: Preview.SurfaceProvider?,
    ) {
        if (session != null || _state.value.starting) return
        _state.value = LiveState(starting = true, status = "Starting camera and models…")
        scope.launch {
            try {
                val s = Session(EngineProvider.get(context))
                withContext(Dispatchers.Default) {
                    s.detector = MediaPipeDetector(context, s.config)
                    // The GPU delegate must live on the thread that runs it.
                    s.depth = s.depthExecutor.submit<MidasDepth> { MidasDepth(context, s.config.android) }.get()
                }
                s.audio = AudioOutput(device, s.mixer::render)
                s.audio.start()
                s.camera.start(owner, preview) { frame -> onFrame(s, frame) }
                session = s
                s.reporter = scope.launch { report(s) }
                val depthLine = "live depth MiDaS small on ${s.depth?.backend}"
                Log.i(LOG_TAG, "REPORT $depthLine")
                _state.value = LiveState(running = true, status = "Sensing. Point the camera ahead.", report = listOf(depthLine))
                launch(Dispatchers.Default) {
                    val arcore = "live ${probeArCoreDepth(context)}"
                    Log.i(LOG_TAG, "REPORT $arcore")
                    _state.value = _state.value.copy(report = _state.value.report + arcore)
                }
            } catch (e: Exception) {
                Log.e(LOG_TAG, "live mode failed to start", e)
                _state.value = LiveState(status = "Could not start: ${e.message}")
            }
        }
    }

    fun stop() {
        val s = session ?: return
        session = null
        s.stopping.set(true)
        s.reporter?.cancel()
        s.camera.stop()
        s.camera.runOnAnalysisThread { s.detector.close() }
        s.camera.shutdown()
        s.depthExecutor.execute { s.depth?.close() }
        s.depthExecutor.shutdown()
        s.audio.stop()
        val summary = "live final: ${s.monitor.format()}, underruns ${s.audio.stats.underruns}"
        Log.i(LOG_TAG, "REPORT $summary")
        _state.value = LiveState(status = "Stopped.", report = _state.value.report + summary)
    }

    private fun onFrame(
        s: Session,
        frame: CameraFrame,
    ) {
        if (s.stopping.get()) return
        try {
            val index = s.frameIndex++
            val bitmap = frame.bitmap
            if (index % s.config.depth.everyNFrames == 0L && s.depthBusy.compareAndSet(false, true)) {
                s.depthExecutor.execute {
                    try {
                        val started = System.nanoTime()
                        s.depth?.let { s.pipeline.submitDepth(it.estimate(bitmap), index) }
                        s.monitor.record("depth", (System.nanoTime() - started) / 1e9)
                    } catch (e: Exception) {
                        Log.e(LOG_TAG, "depth failed", e)
                    } finally {
                        s.depthBusy.set(false)
                    }
                }
            }
            val started = System.nanoTime()
            val detections = s.detector.detect(bitmap)
            s.monitor.record("detection", (System.nanoTime() - started) / 1e9)

            val pixels = IntArray(bitmap.width * bitmap.height)
            bitmap.getPixels(pixels, 0, bitmap.width, 0, 0, bitmap.width, bitmap.height)
            val snapshot =
                s.pipeline.processFrame(
                    Frame(RgbImage(bitmap.width, bitmap.height, pixels), index, frame.arrivalNanos),
                    detections,
                )
            if (frame.arrivalNanos - s.lastPublishNanos > UI_PERIOD_NANOS) {
                s.lastPublishNanos = frame.arrivalNanos
                _state.value = _state.value.copy(objects = snapshot.objects)
            }
        } catch (e: Exception) {
            Log.e(LOG_TAG, "frame processing failed", e)
            _state.value = _state.value.copy(status = "Processing error: ${e.message}")
        }
    }

    private suspend fun report(s: Session) {
        while (scope.isActive) {
            delay(REPORT_PERIOD_MS)
            val sounding = _state.value.objects.count { it.params != null }
            val line =
                "live camera %.1f fps, %d sounding, %d underruns; %s"
                    .format(s.camera.fps, sounding, s.audio.stats.underruns, s.monitor.format())
            Log.i(LOG_TAG, "REPORT $line")
            _state.value = _state.value.copy(latency = line)
        }
    }

    private companion object {
        const val REPORT_PERIOD_MS = 5000L
        const val UI_PERIOD_NANOS = 100_000_000L
    }
}
