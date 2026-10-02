import numpy as np
import pytest

from naadrik.config import Config
from naadrik.sound_engine.mapping import (
    distance_to_pulse_rate,
    height_to_degree,
    map_object,
    quantise_channel,
    rgb_to_levels,
    scale_frequencies,
    x_to_azimuth,
)


def test_scale_spans_configured_octaves(config: Config) -> None:
    freqs = scale_frequencies(config.pitch)
    assert freqs[0] == pytest.approx(config.pitch.base_hz)
    assert np.all(np.diff(freqs) > 0)
    assert freqs[-1] <= config.pitch.base_hz * 2**config.pitch.octaves + 1e-6
    # 2.5 octaves of a 5-note scale: 5 + 5 + the 3 notes of the half octave
    assert len(freqs) == 13


def test_scale_notes_are_pentatonic(config: Config) -> None:
    semitones = np.round(12 * np.log2(scale_frequencies(config.pitch) / config.pitch.base_hz))
    assert set(semitones.astype(int) % 12) == set(config.pitch.scale)


@pytest.mark.parametrize(("y", "expected"), [(0.0, 12), (1.0, 0), (0.5, 6), (-3.0, 12), (7.0, 0)])
def test_height_to_degree_top_is_highest(y: float, expected: int) -> None:
    assert height_to_degree(y, 13) == expected


def test_height_is_monotonic() -> None:
    degrees = [height_to_degree(y, 13) for y in np.linspace(0, 1, 50)]
    assert np.all(np.diff(degrees) <= 0)


def test_distance_endpoints_and_monotonic(config: Config) -> None:
    pulse = config.pulse
    assert distance_to_pulse_rate(0.0, pulse) == pytest.approx(pulse.near_hz)
    assert distance_to_pulse_rate(1.0, pulse) == pytest.approx(pulse.far_hz)
    rates = [distance_to_pulse_rate(d, pulse) for d in np.linspace(0, 1, 20)]
    assert np.all(np.diff(rates) < 0)


def test_distance_is_log_interpolated(config: Config) -> None:
    pulse = config.pulse
    mid = distance_to_pulse_rate(0.5, pulse)
    assert mid == pytest.approx(np.sqrt(pulse.near_hz * pulse.far_hz))


@pytest.mark.parametrize(
    ("value", "level"),
    [(0.0, 0), (0.24, 0), (0.25, 1), (0.59, 1), (0.6, 2), (1.0, 2), (1.5, 2), (-1, 0)],
)
def test_quantise_channel(config: Config, value: float, level: int) -> None:
    assert quantise_channel(value, config.colour) == level


def test_black_is_silent_and_white_is_all_loud(config: Config) -> None:
    off, _, high = config.colour.levels
    assert rgb_to_levels(0, 0, 0, config.colour) == (off, off, off)
    assert rgb_to_levels(1, 1, 1, config.colour) == (high, high, high)


def test_primary_colours_select_one_instrument(config: Config) -> None:
    off, low, high = config.colour.levels
    assert rgb_to_levels(1, 0, 0, config.colour) == (high, off, off)
    assert rgb_to_levels(0, 1, 0, config.colour) == (off, high, off)
    assert rgb_to_levels(0, 0, 0.4, config.colour) == (off, off, low)


def test_azimuth_mapping(config: Config) -> None:
    spatial = config.spatial
    assert x_to_azimuth(0.5, spatial) == 0.0
    assert x_to_azimuth(0.0, spatial) == -spatial.max_azimuth_deg
    assert x_to_azimuth(1.0, spatial) == spatial.max_azimuth_deg


def test_map_object_combines_mappings(config: Config) -> None:
    params = map_object(config, 13, x=0.0, y=0.0, distance=0.0, r=1, g=0, b=0)
    assert params.azimuth_deg < 0
    assert params.degree == 12
    assert params.pulse_hz == pytest.approx(config.pulse.near_hz)
    assert params.levels[0] > 0 and params.levels[1:] == (0.0, 0.0)
    assert not params.is_silent
    assert map_object(config, 13, 0.5, 0.5, 0.5, 0, 0, 0).is_silent
