package com.naadrik.core.sound

import java.util.concurrent.atomic.AtomicReference

/**
 * Real-time mixer: one voice per sounding object.
 *
 * [update] only swaps in a new target set from the perception thread; voice creation and
 * rendering happen in [render] on the audio thread, which therefore never waits on perception.
 */
class LiveMixer(
    private val engine: SoundEngine,
    private val onApplied: ((captureNanos: Long) -> Unit)? = null,
) {
    private class Update(
        val objects: Map<Int, ObjectState>,
        val captureNanos: Long,
    )

    private val pending = AtomicReference<Update?>(null)
    private val voices = LinkedHashMap<Int, Voice>()
    private val releasing = ArrayList<Voice>()

    @Volatile var muted = false

    val activeIds: List<Int> get() = voices.keys.toList()

    fun update(
        objects: Map<Int, ObjectState>,
        captureNanos: Long,
    ) {
        val limited = objects.entries.take(engine.config.objects.maxObjects).associate { it.key to it.value }
        pending.set(Update(limited, captureNanos))
    }

    /** Fill [out] with [frames] interleaved stereo frames. */
    fun render(
        frames: Int,
        out: FloatArray,
    ) {
        pending.getAndSet(null)?.let(::apply)
        out.fill(0f, 0, frames * 2)
        for (voice in voices.values) voice.render(frames, out)
        for (voice in releasing) voice.render(frames, out)
        releasing.removeAll { it.finished }
        if (muted) out.fill(0f, 0, frames * 2)
        engine.master(out, frames)
    }

    private fun apply(update: Update) {
        val gone = voices.keys.filter { it !in update.objects }
        for (id in gone) {
            val voice = voices.remove(id)!!
            voice.release()
            releasing += voice
        }
        for ((id, state) in update.objects) {
            val voice = voices[id]
            if (voice == null) voices[id] = engine.createVoice(state) else voice.target = engine.map(state)
        }
        onApplied?.invoke(update.captureNanos)
    }
}
