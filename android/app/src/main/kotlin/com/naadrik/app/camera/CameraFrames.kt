package com.naadrik.app.camera

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Matrix
import android.util.Log
import android.util.Size
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.ImageProxy
import androidx.camera.core.Preview
import androidx.camera.core.resolutionselector.AspectRatioStrategy
import androidx.camera.core.resolutionselector.ResolutionSelector
import androidx.camera.core.resolutionselector.ResolutionStrategy
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.core.content.ContextCompat
import androidx.lifecycle.LifecycleOwner
import com.naadrik.app.LOG_TAG
import com.naadrik.core.config.Config
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors
import kotlin.math.sqrt

/** An upright, processing-size camera frame and when it reached the app. */
class CameraFrame(
    val bitmap: Bitmap,
    val arrivalNanos: Long,
)

/**
 * CameraX analysis stream that always delivers only the newest frame: if processing falls
 * behind, older frames are dropped rather than queued, so latency never accumulates.
 * Frames are rotated upright and scaled to about camera.process_width x 3/4 of it in pixels.
 */
class CameraFrames(
    private val context: Context,
    private val config: Config,
) {
    private val analysisExecutor: ExecutorService = Executors.newSingleThreadExecutor { Thread(it, "naadrik-detection") }
    private var provider: ProcessCameraProvider? = null
    private var lastArrival = 0L

    @Volatile var fps = 0.0
        private set

    /** Starts the back camera; [onFrame] runs on the detection thread for every frame. */
    fun start(
        owner: LifecycleOwner,
        preview: Preview.SurfaceProvider?,
        onFrame: (CameraFrame) -> Unit,
    ) {
        val future = ProcessCameraProvider.getInstance(context)
        future.addListener({
            val cameraProvider = future.get()
            provider = cameraProvider
            val selector =
                ResolutionSelector
                    .Builder()
                    .setAspectRatioStrategy(AspectRatioStrategy.RATIO_4_3_FALLBACK_AUTO_STRATEGY)
                    .setResolutionStrategy(
                        ResolutionStrategy(
                            Size(config.android.analysisWidth, config.android.analysisHeight),
                            ResolutionStrategy.FALLBACK_RULE_CLOSEST_HIGHER_THEN_LOWER,
                        ),
                    ).build()
            val analysis =
                ImageAnalysis
                    .Builder()
                    .setResolutionSelector(selector)
                    .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                    .setOutputImageFormat(ImageAnalysis.OUTPUT_IMAGE_FORMAT_RGBA_8888)
                    .build()
            analysis.setAnalyzer(analysisExecutor) { image -> deliver(image, onFrame) }
            val useCases =
                listOfNotNull(
                    analysis,
                    preview?.let { surface ->
                        Preview
                            .Builder()
                            .setResolutionSelector(selector)
                            .build()
                            .also { it.surfaceProvider = surface }
                    },
                )
            cameraProvider.unbindAll()
            cameraProvider.bindToLifecycle(owner, CameraSelector.DEFAULT_BACK_CAMERA, *useCases.toTypedArray())
            Log.i(LOG_TAG, "camera bound: analysis ${analysis.resolutionInfo?.resolution}")
        }, ContextCompat.getMainExecutor(context))
    }

    fun stop() {
        provider?.unbindAll()
        provider = null
    }

    /** Runs [block] on the detection thread, after any frame being processed. */
    fun runOnAnalysisThread(block: () -> Unit) = analysisExecutor.execute(block)

    fun shutdown() {
        stop()
        analysisExecutor.shutdown()
    }

    private fun deliver(
        image: ImageProxy,
        onFrame: (CameraFrame) -> Unit,
    ) {
        val arrival = System.nanoTime()
        val upright =
            try {
                upright(image.toBitmap(), image.imageInfo.rotationDegrees)
            } finally {
                image.close()
            }
        if (lastArrival > 0) fps += 0.1 * (1e9 / (arrival - lastArrival) - fps)
        lastArrival = arrival
        onFrame(CameraFrame(upright, arrival))
    }

    private fun upright(
        source: Bitmap,
        rotationDegrees: Int,
    ): Bitmap {
        // Keep roughly the desktop pixel budget (320 x 240) whatever the orientation.
        val target = config.camera.processWidth * config.camera.processWidth * 3.0 / 4.0
        val scale = sqrt(target / (source.width * source.height)).toFloat()
        val matrix =
            Matrix().apply {
                postScale(scale, scale)
                postRotate(rotationDegrees.toFloat())
            }
        return Bitmap.createBitmap(source, 0, 0, source.width, source.height, matrix, true).also {
            if (it !== source) source.recycle()
        }
    }
}
