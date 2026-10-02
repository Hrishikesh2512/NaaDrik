"""Pure mappings from object properties to sound parameters."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from naadrik.config import ColourConfig, Config, PitchConfig, PulseConfig, SpatialConfig


@dataclass(frozen=True)
class SoundParams:
    """Everything needed to sound one object."""

    azimuth_deg: float
    degree: int
    pulse_hz: float
    levels: tuple[float, float, float]

    @property
    def is_silent(self) -> bool:
        return not any(self.levels)


def _clamp01(value: float) -> float:
    return min(max(float(value), 0.0), 1.0)


def scale_frequencies(cfg: PitchConfig) -> np.ndarray:
    """All scale notes from ``base_hz`` up to ``octaves`` above it, ascending."""
    span = cfg.octaves * 12.0
    semitones = [
        octave * 12 + step
        for octave in range(int(np.ceil(cfg.octaves)) + 1)
        for step in cfg.scale
        if octave * 12 + step <= span + 1e-9
    ]
    return cfg.base_hz * 2.0 ** (np.asarray(semitones, dtype=float) / 12.0)


def height_to_degree(y: float, n_degrees: int) -> int:
    """Map vertical position (0 = top of frame) to a scale degree (0 = lowest note)."""
    return round((1.0 - _clamp01(y)) * (n_degrees - 1))


def distance_to_pulse_rate(distance: float, cfg: PulseConfig) -> float:
    """Log-interpolate between near and far rates so each step in distance feels even."""
    return cfg.near_hz * (cfg.far_hz / cfg.near_hz) ** _clamp01(distance)


def quantise_channel(value: float, cfg: ColourConfig) -> int:
    """Return 0 (off), 1 (low) or 2 (high)."""
    low, high = cfg.thresholds
    value = _clamp01(value)
    if value < low:
        return 0
    if value < high:
        return 1
    return 2


def rgb_to_levels(r: float, g: float, b: float, cfg: ColourConfig) -> tuple[float, float, float]:
    """Instrument gains for (pluck, bowed, flute) from an RGB colour in [0, 1]."""
    return tuple(cfg.levels[quantise_channel(channel, cfg)] for channel in (r, g, b))  # type: ignore[return-value]


def x_to_azimuth(x: float, cfg: SpatialConfig) -> float:
    """Map horizontal position (0 = left edge) to azimuth in degrees (negative = left)."""
    return (_clamp01(x) - 0.5) * 2.0 * cfg.max_azimuth_deg


def map_object(
    config: Config,
    n_degrees: int,
    x: float,
    y: float,
    distance: float,
    r: float,
    g: float,
    b: float,
) -> SoundParams:
    return SoundParams(
        azimuth_deg=x_to_azimuth(x, config.spatial),
        degree=height_to_degree(y, n_degrees),
        pulse_hz=distance_to_pulse_rate(distance, config.pulse),
        levels=rgb_to_levels(r, g, b, config.colour),
    )
