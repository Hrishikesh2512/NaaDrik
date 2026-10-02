import numpy as np
import pytest

from naadrik.config import Config
from naadrik.latency import LatencyMonitor
from naadrik.sound_engine import ObjectState, SoundEngine
from naadrik.sound_engine.mixer import LiveMixer


@pytest.fixture(scope="module")
def engine(config: Config) -> SoundEngine:
    return SoundEngine(config)


RED = ObjectState(0.2, 0.3, 0.0, 1, 0, 0)
BLUE = ObjectState(0.8, 0.7, 1.0, 0, 0, 1)


def test_mixer_is_silent_until_updated(engine: SoundEngine) -> None:
    mixer = LiveMixer(engine)
    assert not np.any(mixer.render(256))


def test_mixer_creates_and_releases_voices(engine: SoundEngine) -> None:
    applied: list[float] = []
    mixer = LiveMixer(engine, on_applied=applied.append)
    mixer.update({1: RED, 2: BLUE}, capture_time=12.5)
    block = mixer.render(256)
    assert np.any(block)
    assert sorted(mixer.active_ids) == [1, 2]
    assert applied == [12.5]

    mixer.update({2: BLUE}, capture_time=13.0)
    mixer.render(256)
    assert mixer.active_ids == [2]
    # The released voice rings out briefly, then the far blue object is silent between pulses.
    for _ in range(100):
        mixer.render(256)
    assert mixer.active_ids == [2]


def test_mixer_caps_voices(engine: SoundEngine) -> None:
    mixer = LiveMixer(engine)
    mixer.update({i: RED for i in range(10)}, capture_time=0.0)
    mixer.render(256)
    assert len(mixer.active_ids) == engine.config.objects.max_objects


def test_muted_mixer_is_silent(engine: SoundEngine) -> None:
    mixer = LiveMixer(engine)
    mixer.update({1: RED}, 0.0)
    mixer.muted = True
    assert not np.any(mixer.render(256))


def test_latency_monitor_summary() -> None:
    monitor = LatencyMonitor(window=10)
    for ms in range(1, 21):
        monitor.record("detection", ms / 1000)
    stats = monitor.summary()["detection"]
    assert stats.count == 20
    assert stats.mean_ms == pytest.approx(15.5)  # only the last 10 samples are kept
    assert "detection 16 ms" in monitor.format()
