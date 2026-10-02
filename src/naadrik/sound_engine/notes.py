"""Pre-rendered note bank.

Pitch is quantised to a scale, so the set of notes is small and fixed. Rendering them once at
start-up keeps the real-time path to array slicing and mixing, which cannot stutter.
"""

from __future__ import annotations

import numpy as np

from naadrik.config import Config
from naadrik.sound_engine.instruments import bowed_note, flute_note, pluck_note, presence_note
from naadrik.sound_engine.mapping import scale_frequencies

INSTRUMENTS = ("pluck", "bowed", "flute")
_LOUDNESS_WINDOW_S = 0.3
_TARGET_RMS = 0.2


class NoteBank:
    def __init__(self, config: Config, seed: int = 7) -> None:
        self.sample_rate = config.audio.sample_rate
        self.frequencies = scale_frequencies(config.pitch)
        inst = config.instruments
        rng = np.random.default_rng(seed)
        renderers = (
            (pluck_note, inst.pluck),
            (bowed_note, inst.bowed),
            (flute_note, inst.flute),
        )
        self._notes = np.stack(
            [
                [self._render(render, cfg, f, inst.note_duration_s, rng) for f in self.frequencies]
                for render, cfg in renderers
            ]
        ).astype(np.float32)
        # Always mixed under the colour instruments so an object with no colour is still heard.
        presence = inst.presence
        self._presence_level = presence.level
        self._presence = np.stack(
            [
                _normalise(
                    presence_note(f, self.sample_rate, inst.note_duration_s, presence, rng),
                    self.sample_rate,
                )
                for f in self.frequencies
            ]
        ).astype(np.float32)
        self._mix_cache: dict[tuple[int, tuple[float, ...]], np.ndarray] = {}

    def _render(self, render, cfg, freq: float, duration_s: float, rng) -> np.ndarray:
        note = render(freq, self.sample_rate, duration_s, cfg, rng)
        return _normalise(note, self.sample_rate) * cfg.gain

    @property
    def n_degrees(self) -> int:
        return len(self.frequencies)

    @property
    def note_length(self) -> int:
        return self._notes.shape[-1]

    def note(self, instrument: str, degree: int) -> np.ndarray:
        return self._notes[INSTRUMENTS.index(instrument), degree]

    def presence(self, degree: int) -> np.ndarray:
        """The presence hum at full level; ``mix`` applies ``presence.level``."""
        return self._presence[degree]

    def mix(self, degree: int, levels: tuple[float, float, float]) -> np.ndarray:
        """The presence hum plus the three instruments at one pitch, weighted by colour levels.

        Cached because both inputs are quantised, so the set of combinations is small.
        """
        key = (degree, tuple(levels))
        cached = self._mix_cache.get(key)
        if cached is None:
            weights = np.asarray(levels, dtype=np.float32)[:, None]
            colour = (self._notes[:, degree] * weights).sum(axis=0)
            cached = colour + self._presence_level * self._presence[degree]
            self._mix_cache[key] = cached
        return cached


def _normalise(note: np.ndarray, sr: int) -> np.ndarray:
    """Equalise loudness over the audible gate window, then guarantee no sample exceeds 1."""
    window = note[: int(_LOUDNESS_WINDOW_S * sr)]
    rms = np.sqrt(np.mean(window**2)) + 1e-12
    note = note * (_TARGET_RMS / rms)
    peak = np.max(np.abs(note))
    return note / peak if peak > 1.0 else note
