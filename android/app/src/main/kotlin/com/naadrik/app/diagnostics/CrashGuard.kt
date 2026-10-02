package com.naadrik.app.diagnostics

import android.content.Context
import android.content.SharedPreferences
import android.util.Log
import androidx.core.content.edit
import com.naadrik.app.LOG_TAG
import java.io.File

/**
 * Lets the app survive and explain crashes on phones we cannot attach a debugger to.
 *
 * Risky native initialisation (GPU delegate, ARCore, camera) runs inside [stage]: the stage name
 * is written to disk first and cleared after. A native crash cannot be caught, but on the next
 * launch the stage is still recorded, so the app knows what killed it, skips or falls back from
 * that step, and shows the user what happened. Java exceptions that escape anywhere are saved
 * with their stack trace.
 */
object CrashGuard {
    const val DEPTH_GPU = "depth on the GPU"
    const val DEPTH_GPU_RUN = "first depth run on the GPU"
    const val DEPTH_CPU = "depth on the CPU"
    const val DETECTOR = "object detector"
    const val DETECTOR_RUN = "first detection"
    const val CAMERA = "camera"
    const val ARCORE = "ARCore check"

    private const val PREFS = "crash_guard"
    private const val KEY_STAGE = "stage"
    private const val KEY_FAILED = "failed_stages"
    private const val KEY_VERSION = "version_code"
    private const val TRACE_FILE = "last_crash.txt"

    private lateinit var prefs: SharedPreferences
    private lateinit var traceFile: File

    /** Stages that crashed in an earlier run, in the order they were found. */
    var failedStages: Set<String> = emptySet()
        private set

    /** A message about the previous crash for the user, or null. */
    var previousCrash: String? = null
        private set

    fun install(
        context: Context,
        versionCode: Long,
    ) {
        prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        traceFile = File(context.filesDir, TRACE_FILE)
        // A new build may have fixed what crashed before, so give every step a fresh try.
        if (prefs.getLong(KEY_VERSION, -1L) != versionCode) {
            prefs.edit(commit = true) {
                remove(KEY_FAILED)
                putLong(KEY_VERSION, versionCode)
            }
        }
        val unfinished = prefs.getString(KEY_STAGE, null)
        val failed = prefs.getStringSet(KEY_FAILED, emptySet())!!.toMutableSet()
        val messages = mutableListOf<String>()
        if (unfinished != null) {
            failed += unfinished
            messages += "The last start stopped during: $unfinished."
            prefs.edit(commit = true) {
                remove(KEY_STAGE)
                putStringSet(KEY_FAILED, failed)
            }
        }
        if (traceFile.isFile) {
            messages += "Last error:\n" +
                traceFile
                    .readText()
                    .lines()
                    .take(TRACE_LINES)
                    .joinToString("\n")
            traceFile.delete()
        }
        failedStages = failed
        previousCrash = messages.joinToString("\n").ifEmpty { null }
        previousCrash?.let { Log.e(LOG_TAG, "REPORT previous crash: $it") }

        val previous = Thread.getDefaultUncaughtExceptionHandler()
        Thread.setDefaultUncaughtExceptionHandler { thread, error ->
            runCatching { traceFile.writeText("${thread.name}: ${Log.getStackTraceString(error)}") }
            previous?.uncaughtException(thread, error)
        }
    }

    fun failed(stage: String) = stage in failedStages

    /** Runs [block] with [stage] recorded on disk, so a native crash inside it is attributed. */
    fun <T> stage(
        stage: String,
        block: () -> T,
    ): T {
        // Synchronous writes on purpose: the record must be on disk before a step that may kill
        // the process, which apply() does not guarantee.
        prefs.edit(commit = true) { putString(KEY_STAGE, stage) }
        val result = block()
        prefs.edit(commit = true) { remove(KEY_STAGE) }
        return result
    }

    /** Forget earlier failures, e.g. after an app update that may have fixed them. */
    fun reset() {
        prefs.edit(commit = true) { clear() }
        failedStages = emptySet()
        previousCrash = null
    }

    private const val TRACE_LINES = 12
}
