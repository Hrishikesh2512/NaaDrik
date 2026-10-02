package com.naadrik.app.depth

import android.content.Context
import com.google.ar.core.ArCoreApk
import com.google.ar.core.Config
import com.google.ar.core.Session

/**
 * Whether this phone could use ARCore's Depth API. ARCore needs exclusive use of the camera, so
 * using it means an ARCore-driven frame source instead of CameraX; this probe decides whether
 * that path is worth building for a given device. Needs camera permission.
 */
private const val TRANSIENT_RETRIES = 15
private const val TRANSIENT_WAIT_MS = 200L

fun probeArCoreDepth(context: Context): String =
    try {
        // The first answer is often a transient "checking"; wait briefly for a definite one.
        var availability = ArCoreApk.getInstance().checkAvailability(context)
        var tries = 0
        while (availability.isTransient && tries++ < TRANSIENT_RETRIES) {
            Thread.sleep(TRANSIENT_WAIT_MS)
            availability = ArCoreApk.getInstance().checkAvailability(context)
        }
        if (availability != ArCoreApk.Availability.SUPPORTED_INSTALLED) {
            "arcore $availability, depth not available"
        } else {
            val session = Session(context)
            try {
                val depth = session.isDepthModeSupported(Config.DepthMode.AUTOMATIC)
                "arcore installed, depth supported=$depth"
            } finally {
                session.close()
            }
        }
    } catch (e: Throwable) {
        // Errors too: a missing or mismatched ARCore service can surface as a LinkageError.
        "arcore unavailable: ${e.javaClass.simpleName}"
    }
