import dataclasses

import numpy as np
import pytest

from naadrik.config import Config
from naadrik.spatialiser import (
    Spatialiser,
    interaural_time_difference,
    lateral_angle,
)

SR = 48000


def tone(seconds: float = 0.5, freq: float = 500.0) -> np.ndarray:
    t = np.arange(int(seconds * SR)) / SR
    return np.sin(2 * np.pi * freq * t) + 0.3 * np.sin(2 * np.pi * 3.7 * freq * t)


def render(spatialiser: Spatialiser, x: np.ndarray, azimuth: float, block: int = 256) -> np.ndarray:
    return np.concatenate(
        [spatialiser.process(x[i : i + block], azimuth) for i in range(0, len(x), block)]
    )


def rms(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(x**2)))


def interaural_lag(stereo: np.ndarray) -> int:
    """Samples by which the right channel lags the left (negative: right leads)."""
    left, right = stereo[:, 0], stereo[:, 1]
    corr = np.correlate(right, left, mode="full")
    lags = np.arange(-len(left) + 1, len(left))
    window = np.abs(lags) <= 40
    return int(lags[window][np.argmax(corr[window])])


def test_itd_sign_and_magnitude() -> None:
    assert interaural_time_difference(0.0, 0.0875) == pytest.approx(0.0)
    right = interaural_time_difference(90.0, 0.0875)
    assert 0.0006 < right < 0.0007
    assert interaural_time_difference(-90.0, 0.0875) == pytest.approx(-right)


def test_lateral_angle_folds_rear_sources() -> None:
    assert lateral_angle(150.0) == pytest.approx(lateral_angle(30.0))
    assert lateral_angle(-135.0) == pytest.approx(lateral_angle(-45.0))


@pytest.mark.parametrize("mode", ["head_model", "pan"])
def test_left_source_is_louder_and_earlier_on_left(config: Config, mode: str) -> None:
    cfg = dataclasses.replace(config.spatial, mode=mode)
    out = render(Spatialiser(cfg, SR), tone(), -70.0)[SR // 10 :]
    assert rms(out[:, 0]) > 1.5 * rms(out[:, 1])
    assert interaural_lag(out) > 10


@pytest.mark.parametrize("mode", ["head_model", "pan"])
def test_centre_source_is_balanced(config: Config, mode: str) -> None:
    cfg = dataclasses.replace(config.spatial, mode=mode)
    out = render(Spatialiser(cfg, SR), tone(), 0.0)[SR // 10 :]
    assert rms(out[:, 0]) == pytest.approx(rms(out[:, 1]), rel=1e-3)
    assert interaural_lag(out) == 0


def test_rear_source_is_darker_than_front(config: Config) -> None:
    rng = np.random.default_rng(0)
    noise = rng.standard_normal(SR // 2)

    def high_band_share(stereo: np.ndarray) -> float:
        spectrum = np.abs(np.fft.rfft(stereo.sum(axis=1))) ** 2
        freqs = np.fft.rfftfreq(len(stereo), 1 / SR)
        return float(spectrum[freqs > 5000].sum() / spectrum.sum())

    front = render(Spatialiser(config.spatial, SR), noise, 20.0)
    back = render(Spatialiser(config.spatial, SR), noise, 160.0)
    assert high_band_share(back) < 0.5 * high_band_share(front)


def test_sweep_is_click_free(config: Config) -> None:
    spatialiser = Spatialiser(config.spatial, SR)
    x = tone(1.0, 300.0)
    block = 256
    azimuths = np.linspace(-80, 80, len(x) // block)
    out = np.concatenate(
        [spatialiser.process(x[i * block : (i + 1) * block], az) for i, az in enumerate(azimuths)]
    )
    static_slope = max(
        np.max(np.abs(np.diff(render(Spatialiser(config.spatial, SR), x, az), axis=0)))
        for az in (-80.0, 0.0, 80.0)
    )
    # A click shows up as a sample-to-sample jump far larger than the signal's own slope.
    assert np.max(np.abs(np.diff(out, axis=0))) < 1.2 * static_slope
