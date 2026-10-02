"""Public sound-engine API: turn object descriptions into spatialised audio."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass

import numpy as np

from naadrik.config import Config
from naadrik.sound_engine.mapping import SoundParams, map_object
from naadrik.sound_engine.notes import NoteBank
from naadrik.sound_engine.voice import Voice, staggered_phase

_LIMITER_KNEE = 0.8


@dataclass(frozen=True)
class ObjectState:
    """An object as the sound engine sees it. All values are normalised to [0, 1]."""

    x: float
    y: float
    distance: float
    r: float
    g: float
    b: float


class SoundEngine:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.sample_rate = config.audio.sample_rate
        self.bank = NoteBank(config)

    def map(self, obj: ObjectState) -> SoundParams:
        return map_object(
            self.config, self.bank.n_degrees, obj.x, obj.y, obj.distance, obj.r, obj.g, obj.b
        )

    def create_voice(self, obj: ObjectState, sounding: Iterable[Voice] = ()) -> Voice:
        """A voice for ``obj``, its pulses interleaved with similar-rate voices in ``sounding``."""
        params = self.map(obj)
        return Voice(self.bank, self.config, params, staggered_phase(params.pulse_hz, sounding))

    def render_object(
        self,
        x: float,
        y: float,
        distance: float,
        r: float,
        g: float,
        b: float,
        duration_s: float = 2.0,
    ) -> np.ndarray:
        """Render one static object to a float32 stereo buffer of shape (frames, 2)."""
        return self.render_scene([ObjectState(x, y, distance, r, g, b)], duration_s)

    def render_scene(self, objects: Sequence[ObjectState], duration_s: float = 2.0) -> np.ndarray:
        """Render static objects together; only the first ``max_objects`` are sounded."""
        limited = list(objects)[: self.config.objects.max_objects]
        return self.render_paths([_constant(obj) for obj in limited], duration_s)

    def render_paths(
        self, paths: Sequence[Callable[[float], ObjectState]], duration_s: float
    ) -> np.ndarray:
        """Render objects whose state changes over time; each path maps seconds to a state."""
        block = self.config.audio.block_size
        total = int(duration_s * self.sample_rate)
        voices: list[Voice] = []
        for path in paths:
            voices.append(self.create_voice(path(0.0), voices))
        out = np.zeros((total, 2), dtype=np.float32)
        for start in range(0, total, block):
            n = min(block, total - start)
            t = start / self.sample_rate
            for voice, path in zip(voices, paths, strict=True):
                voice.update(self.map(path(t)))
                out[start : start + n] += voice.render(n)
        return self.master(out)

    def master(self, mix: np.ndarray) -> np.ndarray:
        return soft_clip(mix * self.config.audio.master_gain).astype(np.float32)


def soft_clip(x: np.ndarray, knee: float = _LIMITER_KNEE) -> np.ndarray:
    """Linear below the knee, then a tanh shoulder that never exceeds 1."""
    magnitude = np.abs(x)
    shoulder = knee + (1.0 - knee) * np.tanh((magnitude - knee) / (1.0 - knee))
    return np.where(magnitude <= knee, x, np.sign(x) * shoulder)


def _constant(obj: ObjectState) -> Callable[[float], ObjectState]:
    return lambda _t: obj
