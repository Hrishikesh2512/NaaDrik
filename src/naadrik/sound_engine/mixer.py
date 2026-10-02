"""Real-time mixer: one voice per sounding object, driven from the audio callback."""

from __future__ import annotations

import threading
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass

import numpy as np

from naadrik.sound_engine.engine import ObjectState, SoundEngine
from naadrik.sound_engine.voice import Voice
from naadrik.spatialiser import Spatialiser


@dataclass
class _Announcement:
    object_id: int
    samples: np.ndarray
    position: int = 0
    gap_left: int = 0

    @property
    def speaking(self) -> bool:
        return self.position < len(self.samples)


class LiveMixer:
    """Receives object updates from the perception thread and renders them on the audio thread.

    ``update`` only swaps in a new target set; all voice creation and rendering happens in
    ``render`` so the audio thread never waits on perception.

    Training mode adds spoken announcements. An announced object's voice is held back until
    its label has been spoken, so the user hears the description first and then the sound
    it describes. Other voices are ducked while speech plays.
    """

    def __init__(
        self,
        engine: SoundEngine,
        on_applied: Callable[[float], None] | None = None,
        duck_db: float = 0.0,
        gap_s: float = 0.0,
        spatialise_speech: bool = True,
    ) -> None:
        self._engine = engine
        self._on_applied = on_applied
        self._lock = threading.Lock()
        self._pending: tuple[dict[int, ObjectState], float] | None = None
        self._pending_announcements: list[tuple[int, np.ndarray]] = []
        self._voices: dict[int, Voice] = {}
        self._releasing: list[Voice] = []
        self._announcements: deque[_Announcement] = deque()
        self._speech_spatialiser = Spatialiser(engine.config.spatial, engine.sample_rate)
        self._spatialise_speech = spatialise_speech
        self._duck_gain = 10.0 ** (-duck_db / 20.0)
        self._gap = int(gap_s * engine.sample_rate)
        self._current_duck = 1.0
        self.muted = False

    @property
    def active_ids(self) -> list[int]:
        return list(self._voices)

    @property
    def speaking(self) -> bool:
        return bool(self._announcements)

    def update(
        self,
        objects: Mapping[int, ObjectState],
        capture_time: float,
        announcements: Mapping[int, np.ndarray] | None = None,
    ) -> None:
        limited = dict(list(objects.items())[: self._engine.config.objects.max_objects])
        with self._lock:
            self._pending = (limited, capture_time)
            if announcements:
                self._pending_announcements.extend(announcements.items())

    def render(self, frames: int) -> np.ndarray:
        with self._lock:
            pending, self._pending = self._pending, None
            announcements, self._pending_announcements = self._pending_announcements, []
        if pending is not None:
            self._apply(*pending)
        for object_id, samples in announcements:
            self._announcements.append(_Announcement(object_id, samples, gap_left=self._gap))

        held = self._announcements[0].object_id if self._announcements else None
        queued = {a.object_id for a in self._announcements}
        voices = np.zeros((frames, 2), dtype=np.float32)
        for object_id, voice in self._voices.items():
            # Objects waiting to be announced stay silent; the one being announced too.
            if object_id != held and object_id not in queued:
                voices += voice.render(frames)
        for voice in self._releasing:
            voices += voice.render(frames)
        self._releasing = [voice for voice in self._releasing if not voice.finished]

        speech = self._render_speech(frames)
        mix = voices * self._duck_ramp(frames, speech is not None)
        if speech is not None:
            mix += speech
        if self.muted:
            mix.fill(0.0)
        return self._engine.master(mix)

    def _apply(self, objects: dict[int, ObjectState], capture_time: float) -> None:
        for object_id in list(self._voices):
            if object_id not in objects:
                voice = self._voices.pop(object_id)
                voice.release()
                self._releasing.append(voice)
        self._announcements = deque(a for a in self._announcements if a.object_id in objects)
        for object_id, state in objects.items():
            voice = self._voices.get(object_id)
            if voice is None:
                self._voices[object_id] = self._engine.create_voice(state, self._voices.values())
            else:
                voice.update(self._engine.map(state))
        if self._on_applied is not None:
            self._on_applied(capture_time)

    def _render_speech(self, frames: int) -> np.ndarray | None:
        if not self._announcements:
            return None
        current = self._announcements[0]
        mono = np.zeros(frames, dtype=np.float32)
        if current.speaking:
            chunk = current.samples[current.position : current.position + frames]
            mono[: len(chunk)] = chunk
            current.position += len(chunk)
        else:
            current.gap_left -= frames
            if current.gap_left <= 0:
                self._announcements.popleft()
        voice = self._voices.get(current.object_id)
        azimuth = voice.target.azimuth_deg if voice is not None and self._spatialise_speech else 0.0
        return self._speech_spatialiser.process(mono, azimuth)

    def _duck_ramp(self, frames: int, ducking: bool) -> np.ndarray:
        target = self._duck_gain if ducking else 1.0
        ramp = np.linspace(self._current_duck, target, frames, dtype=np.float32)[:, None]
        self._current_duck = target
        return ramp
