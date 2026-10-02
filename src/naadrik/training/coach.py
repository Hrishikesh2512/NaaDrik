"""Decides when to announce an object: when it starts sounding and again every ``repeat_s``."""

from __future__ import annotations

import random
from collections.abc import Callable, Iterable
from dataclasses import dataclass

import numpy as np

from naadrik.config import Config
from naadrik.sound_engine import ObjectState
from naadrik.training.describe import describe


@dataclass(frozen=True)
class Candidate:
    object_id: int
    label: str
    state: ObjectState


class TrainingCoach:
    def __init__(
        self,
        config: Config,
        say: Callable[[str], np.ndarray],
        probability: float,
        rng: random.Random | None = None,
    ) -> None:
        self._config = config
        self._say = say
        self._probability = probability
        self._rng = rng or random.Random()
        self._last_considered: dict[int, float] = {}
        self.spoken: list[str] = []

    @property
    def probability(self) -> float:
        return self._probability

    def announcements(self, candidates: Iterable[Candidate], now: float) -> dict[int, np.ndarray]:
        repeat = self._config.training.repeat_s
        clips: dict[int, np.ndarray] = {}
        for candidate in candidates:
            last = self._last_considered.get(candidate.object_id)
            if last is not None and now - last < repeat:
                continue
            self._last_considered[candidate.object_id] = now
            # Each due announcement is kept or skipped independently, so speech thins out
            # gradually across a session rather than stopping for whole objects.
            if self._rng.random() >= self._probability:
                continue
            text = describe(candidate.label, candidate.state, self._config)
            clips[candidate.object_id] = self._say(text)
            self.spoken.append(text)
        self._forget_older_than(now - 10 * repeat)
        return clips

    def _forget_older_than(self, cutoff: float) -> None:
        self._last_considered = {k: t for k, t in self._last_considered.items() if t >= cutoff}
