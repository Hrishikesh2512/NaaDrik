"""A voice sounds one object: it pulses notes at the object's rate and places them in space."""

from __future__ import annotations

import itertools
import math
from collections.abc import Iterable
from dataclasses import dataclass

import numpy as np

from naadrik.config import Config
from naadrik.sound_engine.mapping import SoundParams
from naadrik.sound_engine.notes import NoteBank
from naadrik.spatialiser import Spatialiser


@dataclass
class _NoteEvent:
    samples: np.ndarray
    end: int  # gate + release, in samples from the note start
    gate: int
    offset: int  # where the note starts within the block being rendered
    position: int = 0

    @property
    def finished(self) -> bool:
        return self.position >= self.end


class Voice:
    def __init__(
        self, bank: NoteBank, config: Config, params: SoundParams, initial_phase: float = 1.0
    ) -> None:
        self._bank = bank
        self._pulse = config.pulse
        self._sr = config.audio.sample_rate
        self._smoothing_samples = config.spatial.smoothing_ms / 1000.0 * self._sr
        self._attack = max(1, int(self._pulse.attack_ms / 1000.0 * self._sr))
        self._release = max(1, int(self._pulse.release_ms / 1000.0 * self._sr))
        self._spatialiser = Spatialiser(config.spatial, self._sr)
        self.target = params
        self._azimuth = params.azimuth_deg
        self._rate = params.pulse_hz
        # Progress (0..1) from the last pulse to the next; 1 sounds a pulse immediately.
        self._phase = initial_phase
        self._events: list[_NoteEvent] = []
        self._released = False

    @property
    def azimuth_deg(self) -> float:
        return self._azimuth

    @property
    def pulse_hz(self) -> float:
        return self._rate

    @property
    def phase(self) -> float:
        return self._phase

    @property
    def finished(self) -> bool:
        return self._released and not self._events

    def update(self, params: SoundParams) -> None:
        self.target = params

    def release(self) -> None:
        """Stop pulsing; notes already sounding ring out through their release."""
        self._released = True

    def render(self, n: int) -> np.ndarray:
        self._glide(n)
        if not self._released:
            self._schedule_pulses(n)
        mono = np.zeros(n)
        for event in self._events:
            self._render_event(event, mono)
        self._events = [event for event in self._events if not event.finished]
        return self._spatialiser.process(mono, self._azimuth)

    def _glide(self, n: int) -> None:
        keep = math.exp(-n / self._smoothing_samples) if self._smoothing_samples > 0 else 0.0
        self._azimuth = self.target.azimuth_deg + (self._azimuth - self.target.azimuth_deg) * keep
        # Glide rate in the log domain, matching how distance is mapped to rate.
        log_rate = (
            math.log(self.target.pulse_hz)
            + (math.log(self._rate) - math.log(self.target.pulse_hz)) * keep
        )
        self._rate = math.exp(log_rate)

    def _schedule_pulses(self, n: int) -> None:
        step = self._rate / self._sr
        position = 0
        while True:
            to_next = max(0, math.ceil((1.0 - self._phase) / step))
            if position + to_next >= n:
                self._phase += step * (n - position)
                return
            position += to_next
            self._phase = 0.0
            self._start_note(position)

    def _start_note(self, offset: int) -> None:
        gate_s = min(self._pulse.duty_cycle / self._rate, self._pulse.max_gate_s)
        gate = int(gate_s * self._sr)
        samples = self._bank.mix(self.target.degree, self.target.levels)
        end = min(gate + self._release, len(samples))
        self._events.append(_NoteEvent(samples, end=end, gate=gate, offset=offset))

    def _render_event(self, event: _NoteEvent, mono: np.ndarray) -> None:
        count = min(len(mono) - event.offset, event.end - event.position)
        if count > 0:
            index = event.position + np.arange(count)
            attack = np.minimum(index / self._attack, 1.0)
            release = np.clip((event.end - index) / self._release, 0.0, 1.0)
            segment = event.samples[event.position : event.position + count]
            mono[event.offset : event.offset + count] += segment * attack * release
        event.position += max(count, 0)
        event.offset = 0


_SIMILAR_RATE_RATIO = 1.25


def staggered_phase(pulse_hz: float, others: Iterable[Voice]) -> float:
    """Starting phase that puts a new voice's pulses in the largest gap between similar voices.

    Two sounds with the same pitch and pulse rate whose onsets coincide fuse into one phantom
    image in the centre of the head, so two objects at the same height and distance would be
    heard as one. Interleaving the onsets keeps them separate. Alone, a voice starts at once.
    """
    phases = sorted(
        voice.phase % 1.0
        for voice in others
        if not voice.finished
        and abs(math.log(voice.pulse_hz / pulse_hz)) < math.log(_SIMILAR_RATE_RATIO)
    )
    if not phases:
        return 1.0
    best_start, best_gap = phases[-1], phases[0] + 1.0 - phases[-1]
    for previous, current in itertools.pairwise(phases):
        if current - previous > best_gap:
            best_start, best_gap = previous, current - previous
    middle = (best_start + best_gap / 2.0) % 1.0
    return middle or 1.0
