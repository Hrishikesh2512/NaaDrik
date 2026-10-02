package com.naadrik.app.ui

import android.graphics.Paint
import androidx.camera.view.PreviewView
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.nativeCanvas
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import com.naadrik.app.live.LiveState
import com.naadrik.core.perception.ObjectView
import kotlin.math.log2
import kotlin.math.roundToInt

private val NOTE_NAMES = listOf("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
private val SOUNDING = Color(0xFF3CDC3C)
private val TRACKED = Color(0xFF9E9E9E)

fun noteName(freqHz: Double): String {
    val midi = (69 + 12 * log2(freqHz / 440.0)).roundToInt()
    return "${NOTE_NAMES[midi % 12]}${midi / 12 - 1}"
}

private fun third(
    value: Double,
    names: List<String>,
) = names[(value.coerceIn(0.0, 1.0) * 3).toInt().coerceAtMost(2)]

/** One line per object, phrased for a sighted helper and for TalkBack alike. */
fun describe(
    obj: ObjectView,
    frequencies: DoubleArray,
): String {
    val where = third(obj.box.centreX, listOf("left", "centre", "right"))
    val distance = third(obj.soundDistance, listOf("near", "mid distance", "far"))
    val params = obj.params ?: return "${obj.label}, $where, $distance (not sounding)"
    val levels =
        listOf("sitar" to params.levels.pluck, "violin" to params.levels.bowed, "flute" to params.levels.flute)
            .filter { it.second > 0 }
            .joinToString(" ") { it.first }
            .ifEmpty { "hum only" }
    val pitch = noteName(frequencies[params.degree])
    return "${obj.label}, $where, $distance: $pitch, %.1f pulses per second, $levels".format(params.pulseHz)
}

@Composable
fun LiveScreen(
    state: LiveState,
    previewView: PreviewView,
    frequencies: DoubleArray?,
    onStart: () -> Unit,
    onStop: () -> Unit,
) {
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item {
            Text("Live sensing", style = MaterialTheme.typography.headlineMedium, modifier = Modifier.semantics { heading() })
        }
        item {
            Text(
                state.status,
                style = MaterialTheme.typography.titleMedium,
                modifier =
                    Modifier.semantics {
                        liveRegion =
                            LiveRegionMode.Polite
                    },
            )
        }
        item {
            Button(
                onClick = if (state.running) onStop else onStart,
                enabled = !state.starting,
                modifier = Modifier.fillMaxWidth().heightIn(min = 96.dp),
            ) { Text(if (state.running) "Stop" else "Start", style = MaterialTheme.typography.headlineSmall) }
        }
        item {
            // The preview and boxes help sighted testers; TalkBack users get the text below.
            Box(Modifier.fillMaxWidth().aspectRatio(3f / 4f).clearAndSetSemantics { }) {
                AndroidView(factory = { previewView }, modifier = Modifier.fillMaxSize())
                if (state.running) Overlay(state.objects)
            }
        }
        if (frequencies != null) {
            items(state.objects.filter { it.params != null }) { obj ->
                Text(describe(obj, frequencies), style = MaterialTheme.typography.bodyLarge)
            }
        }
        if (state.latency.isNotEmpty()) item { Text(state.latency, style = MaterialTheme.typography.bodySmall) }
        items(state.report) { Text(it, style = MaterialTheme.typography.bodySmall) }
    }
}

@Composable
private fun Overlay(objects: List<ObjectView>) {
    val paint =
        Paint().apply {
            textSize = 36f
            isAntiAlias = true
        }
    Canvas(Modifier.fillMaxSize()) {
        for (obj in objects) {
            val sounding = obj.params != null
            val topLeft = Offset((obj.box.x0 * size.width).toFloat(), (obj.box.y0 * size.height).toFloat())
            val boxSize = Size((obj.box.width * size.width).toFloat(), (obj.box.height * size.height).toFloat())
            drawRect(if (sounding) SOUNDING else TRACKED, topLeft, boxSize, style = Stroke(width = if (sounding) 6f else 2f))
            paint.color = if (sounding) android.graphics.Color.GREEN else android.graphics.Color.LTGRAY
            val label = obj.label + (obj.distance?.let { " d=%.2f".format(it) } ?: "")
            drawContext.canvas.nativeCanvas.drawText(label, topLeft.x + 8f, (topLeft.y + 40f).coerceAtLeast(40f), paint)
        }
    }
}
