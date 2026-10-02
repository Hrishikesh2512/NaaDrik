import numpy as np
import pytest

from naadrik.config import Config
from naadrik.sound_engine import ObjectState, SoundEngine
from naadrik.sound_engine.voice import Voice, staggered_phase

OBJ = ObjectState(0.5, 0.5, 0.2, 1.0, 0.0, 0.0)


@pytest.fixture(scope="module")
def engine(config: Config) -> SoundEngine:
    return SoundEngine(config)


def voice_at(engine: SoundEngine, phase: float, obj: ObjectState = OBJ) -> Voice:
    return Voice(engine.bank, engine.config, engine.map(obj), phase)


def test_alone_starts_immediately(engine: SoundEngine) -> None:
    assert staggered_phase(engine.map(OBJ).pulse_hz, []) == 1.0


def test_second_voice_lands_halfway(engine: SoundEngine) -> None:
    rate = engine.map(OBJ).pulse_hz
    assert staggered_phase(rate, [voice_at(engine, 1.0)]) == pytest.approx(0.5)
    assert staggered_phase(rate, [voice_at(engine, 0.2)]) == pytest.approx(0.7)


def test_different_rates_are_not_staggered(engine: SoundEngine) -> None:
    far = ObjectState(0.5, 0.5, 1.0, 1.0, 0.0, 0.0)
    assert staggered_phase(engine.map(OBJ).pulse_hz, [voice_at(engine, 1.0, far)]) == 1.0


def test_equal_objects_pulse_half_a_period_apart(engine: SoundEngine) -> None:
    left = engine.create_voice(ObjectState(0.1, 0.5, 0.2, 1.0, 0.0, 0.0))
    right = engine.create_voice(ObjectState(0.9, 0.5, 0.2, 1.0, 0.0, 0.0), [left])

    def first_onset(voice: Voice) -> int:
        out = np.concatenate([voice.render(256) for _ in range(187)])
        return int(np.flatnonzero(np.abs(out).sum(axis=1) > 1e-4)[0])

    offset_s = (first_onset(right) - first_onset(left)) / engine.sample_rate
    assert offset_s == pytest.approx(0.5 / engine.map(OBJ).pulse_hz, abs=0.01)
