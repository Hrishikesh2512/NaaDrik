"""Real-time mixer: one voice per sounding object, driven from the audio callback."""

from __future__ import annotations

import threading
from collections.abc import Callable, Mapping

import numpy as np

from naadrik.sound_engine.engine import ObjectState, SoundEngine
from naadrik.sound_engine.voice import Voice


class LiveMixer:
    """Receives object updates from the perception thread and renders them on the audio thread.

    ``update`` only swaps in a new target set; all voice creation and rendering happens in
    ``render`` so the audio thread never waits on perception.
    """

    def __init__(
        self, engine: SoundEngine, on_applied: Callable[[float], None] | None = None
    ) -> None:
        self._engine = engine
        self._on_applied = on_applied
        self._lock = threading.Lock()
        self._pending: tuple[dict[int, ObjectState], float] | None = None
        self._voices: dict[int, Voice] = {}
        self._releasing: list[Voice] = []
        self.muted = False

    @property
    def active_ids(self) -> list[int]:
        return list(self._voices)

    def update(self, objects: Mapping[int, ObjectState], capture_time: float) -> None:
        limited = dict(list(objects.items())[: self._engine.config.objects.max_objects])
        with self._lock:
            self._pending = (limited, capture_time)

    def render(self, frames: int) -> np.ndarray:
        with self._lock:
            pending, self._pending = self._pending, None
        if pending is not None:
            self._apply(*pending)
        mix = np.zeros((frames, 2), dtype=np.float32)
        for voice in [*self._voices.values(), *self._releasing]:
            mix += voice.render(frames)
        self._releasing = [voice for voice in self._releasing if not voice.finished]
        if self.muted:
            mix.fill(0.0)
        return self._engine.master(mix)

    def _apply(self, objects: dict[int, ObjectState], capture_time: float) -> None:
        for object_id in list(self._voices):
            if object_id not in objects:
                voice = self._voices.pop(object_id)
                voice.release()
                self._releasing.append(voice)
        for object_id, state in objects.items():
            voice = self._voices.get(object_id)
            if voice is None:
                self._voices[object_id] = self._engine.create_voice(state)
            else:
                voice.update(self._engine.map(state))
        if self._on_applied is not None:
            self._on_applied(capture_time)
