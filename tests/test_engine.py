import numpy as np
import pytest

from naadrik.config import Config
from naadrik.sound_engine import ObjectState, SoundEngine, soft_clip


@pytest.fixture(scope="module")
def engine(config: Config) -> SoundEngine:
    return SoundEngine(config)


def count_pulses(stereo: np.ndarray, sr: int, min_gap_s: float = 0.02) -> int:
    """Count notes that start after at least ``min_gap_s`` of silence."""
    active = np.abs(stereo).sum(axis=1) > 1e-4
    gap = int(min_gap_s * sr)
    # True while any sample in the trailing gap window is active, so zero crossings inside a
    # note do not split it; a rising edge therefore marks a note after real silence.
    held = np.convolve(active, np.ones(gap), mode="full")[: len(active)] > 0
    return int(held[0]) + int(np.sum(np.diff(held.astype(int)) == 1))


def channel_rms(stereo: np.ndarray) -> tuple[float, float]:
    left, right = np.sqrt(np.mean(stereo**2, axis=0))
    return float(left), float(right)


def test_render_object_shape_and_range(engine: SoundEngine) -> None:
    out = engine.render_object(0.2, 0.3, 0.5, 1.0, 0.5, 0.0, duration_s=1.0)
    assert out.shape == (engine.sample_rate, 2)
    assert out.dtype == np.float32
    assert np.all(np.isfinite(out))
    assert np.max(np.abs(out)) <= 1.0


def test_black_object_is_silent(engine: SoundEngine) -> None:
    assert not np.any(engine.render_object(0.5, 0.5, 0.0, 0.0, 0.0, 0.0, duration_s=0.5))


@pytest.mark.parametrize(("distance", "expected_rate"), [(0.0, 8.0), (1.0, 1.0)])
def test_pulse_rate_follows_distance(
    engine: SoundEngine, distance: float, expected_rate: float
) -> None:
    seconds = 3.0
    out = engine.render_object(0.5, 0.5, distance, 0.0, 0.0, 1.0, duration_s=seconds)
    assert count_pulses(out, engine.sample_rate) == pytest.approx(expected_rate * seconds, abs=1)


def test_left_object_is_louder_on_left(engine: SoundEngine) -> None:
    left, right = channel_rms(engine.render_object(0.0, 0.5, 0.3, 0, 1, 0, duration_s=1.0))
    assert left > 1.5 * right
    left, right = channel_rms(engine.render_object(1.0, 0.5, 0.3, 0, 1, 0, duration_s=1.0))
    assert right > 1.5 * left


def test_distance_does_not_change_note_loudness(engine: SoundEngine) -> None:
    def first_note_peak(distance: float) -> float:
        out = engine.render_object(0.5, 0.5, distance, 1, 0, 0, duration_s=0.1)
        return float(np.max(np.abs(out)))

    assert first_note_peak(0.0) == pytest.approx(first_note_peak(1.0), rel=0.05)


def test_brighter_colour_is_louder(engine: SoundEngine) -> None:
    def loudness(rgb: tuple[float, float, float]) -> float:
        return sum(channel_rms(engine.render_object(0.5, 0.5, 0.2, *rgb, duration_s=1.0)))

    assert loudness((0.4, 0.4, 0.4)) < loudness((1.0, 1.0, 1.0))
    assert loudness((1.0, 0.0, 0.0)) < loudness((1.0, 1.0, 1.0))


def test_scene_caps_object_count(engine: SoundEngine) -> None:
    red = ObjectState(0.5, 0.5, 0.5, 1, 0, 0)
    blue = ObjectState(0.5, 0.5, 0.5, 0, 0, 1)
    capped = engine.render_scene([red] * engine.config.objects.max_objects + [blue], 0.5)
    np.testing.assert_allclose(capped, engine.render_scene([red] * 3, 0.5))


def test_moving_object_has_no_clicks(engine: SoundEngine) -> None:
    def sweep(t: float) -> ObjectState:
        return ObjectState(t / 2.0, 0.5, 0.3, 0, 0, 1)

    moving = engine.render_paths([sweep], 2.0)
    static = engine.render_object(0.0, 0.5, 0.3, 0, 0, 1, duration_s=2.0)
    assert np.max(np.abs(np.diff(moving, axis=0))) < 1.5 * np.max(np.abs(np.diff(static, axis=0)))


def test_soft_clip_is_transparent_below_knee_and_bounded() -> None:
    x = np.linspace(-0.79, 0.79, 101)
    np.testing.assert_allclose(soft_clip(x), x)
    assert np.max(np.abs(soft_clip(np.array([-50.0, 3.0, 50.0])))) <= 1.0
