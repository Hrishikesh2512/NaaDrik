package com.naadrik.app.depth

import android.content.Context
import android.graphics.Bitmap
import android.util.Log
import androidx.core.graphics.scale
import com.naadrik.app.LOG_TAG
import com.naadrik.core.config.AndroidConfig
import com.naadrik.core.perception.DisparityMap
import org.tensorflow.lite.Interpreter
import org.tensorflow.lite.gpu.CompatibilityList
import org.tensorflow.lite.gpu.GpuDelegate
import java.io.FileInputStream
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.nio.MappedByteBuffer
import java.nio.channels.FileChannel

/**
 * MiDaS v2.1 small: relative inverse depth (larger = nearer) at 256 x 256, the same meaning as
 * the desktop's Depth Anything output, so the same normalisation applies.
 *
 * The GPU delegate must be created and used on one thread; construct and call this from the
 * depth thread only.
 */
class MidasDepth(
    context: Context,
    private val cfg: AndroidConfig,
) : AutoCloseable {
    private val size = cfg.depthInputSize
    private var gpu: GpuDelegate? = null
    private val interpreter: Interpreter
    private val input = ByteBuffer.allocateDirect(size * size * 3 * 4).order(ByteOrder.nativeOrder())
    private val output = ByteBuffer.allocateDirect(size * size * 4).order(ByteOrder.nativeOrder())
    private val pixels = IntArray(size * size)

    /** "gpu" or "cpu (N threads)", for the report. */
    val backend: String

    init {
        val model = mapAsset(context, cfg.depthModel)
        var chosen: Interpreter? = null
        var label = "cpu (${cfg.depthThreads} threads)"
        val compatibility = CompatibilityList()
        if (cfg.depthDelegate == "gpu" && compatibility.isDelegateSupportedOnThisDevice) {
            try {
                val delegate = GpuDelegate(compatibility.bestOptionsForThisDevice)
                chosen = Interpreter(model, Interpreter.Options().addDelegate(delegate))
                gpu = delegate
                label = "gpu"
            } catch (e: Throwable) {
                // Errors too: a missing OpenCL/GL driver surfaces as a LinkageError.
                gpu?.close()
                gpu = null
                Log.w(LOG_TAG, "GPU delegate unavailable, using CPU: $e")
            }
        }
        interpreter = chosen ?: Interpreter(model, Interpreter.Options().setNumThreads(cfg.depthThreads))
        backend = label
    }

    fun estimate(frame: Bitmap): DisparityMap {
        val scaled = frame.scale(size, size)
        scaled.getPixels(pixels, 0, size, 0, 0, size, size)
        if (scaled !== frame) scaled.recycle()
        input.rewind()
        for (p in pixels) {
            input.putFloat((((p shr 16) and 0xFF) / 255f - MEAN[0]) / STD[0])
            input.putFloat((((p shr 8) and 0xFF) / 255f - MEAN[1]) / STD[1])
            input.putFloat(((p and 0xFF) / 255f - MEAN[2]) / STD[2])
        }
        input.rewind()
        output.rewind()
        interpreter.run(input, output)
        output.rewind()
        val values = FloatArray(size * size)
        output.asFloatBuffer().get(values)
        return DisparityMap(size, size, values)
    }

    override fun close() {
        interpreter.close()
        gpu?.close()
    }

    private companion object {
        val MEAN = floatArrayOf(0.485f, 0.456f, 0.406f)
        val STD = floatArrayOf(0.229f, 0.224f, 0.225f)

        fun mapAsset(
            context: Context,
            name: String,
        ): MappedByteBuffer =
            context.assets.openFd(name).use { fd ->
                FileInputStream(fd.fileDescriptor).channel.use { channel ->
                    channel.map(FileChannel.MapMode.READ_ONLY, fd.startOffset, fd.declaredLength)
                }
            }
    }
}
