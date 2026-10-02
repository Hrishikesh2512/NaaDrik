"""Baseline sonifier modelled on Peter Meijer's classic vOICe mapping, for comparison.

A greyscale image is scanned left to right once per sweep. Each row drives a sine whose
frequency rises exponentially from the bottom row to the top; a pixel's brightness sets that
sine's loudness while its column is being scanned, and the sound pans from left to right
with the scan. There is no distance or colour channel: distance appears only as apparent
size and colour only as grey level.
"""

from __future__ import annotations

import numpy as np

from naadrik.config import BaselineSonifierConfig
from naadrik.stimuli import COLOURS, Stimulus

# Apparent radius of the object disc (fraction of image width) per distance.
DISC_RADIUS = {"near": 0.22, "mid": 0.13, "far": 0.07}
_LUMA = np.array([0.299, 0.587, 0.114])
_CLICK_S = 0.004


def grey_level(colour: str, mode: str) -> float:
    rgb = np.asarray(COLOURS[colour])
    return float(rgb @ _LUMA) if mode == "luma" else float(rgb.mean())


def stimulus_image(stimulus: Stimulus, cfg: BaselineSonifierConfig) -> np.ndarray:
    """Greyscale image (rows x columns, 0..1) of the stimulus: a disc on a black background."""
    state = stimulus.state()
    rows, cols = cfg.rows, cfg.columns
    y, x = np.mgrid[0:rows, 0:cols]
    # Square pixels in normalised width units so the disc stays round.
    px = (x + 0.5) / cols
    py = (y + 0.5) / rows * rows / cols
    cy = state.y * rows / cols
    inside = (px - state.x) ** 2 + (py - cy) ** 2 <= DISC_RADIUS[stimulus.distance] ** 2
    return inside * grey_level(stimulus.colour, cfg.greyscale)


def row_frequencies(cfg: BaselineSonifierConfig) -> np.ndarray:
    """Frequency per row, top row highest."""
    steps = np.arange(cfg.rows)[::-1] / (cfg.rows - 1)
    return cfg.low_hz * (cfg.high_hz / cfg.low_hz) ** steps


class BaselineSonifier:
    def __init__(self, cfg: BaselineSonifierConfig, sample_rate: int) -> None:
        self._cfg = cfg
        self._sr = sample_rate
        self._freqs = row_frequencies(cfg)

    def render_image(self, image: np.ndarray, duration_s: float) -> np.ndarray:
        """Stereo float32 audio of repeated sweeps over ``image`` for ``duration_s``."""
        cfg = self._cfg
        total = int(duration_s * self._sr)
        t = np.arange(total) / self._sr
        sweep_position = (t % cfg.sweep_s) / cfg.sweep_s  # 0..1 within each sweep
        column_float = sweep_position * cfg.columns - 0.5
        # Interpolate column amplitudes in time so column boundaries do not click.
        columns = np.arange(cfg.columns)
        amplitudes = np.stack([np.interp(column_float, columns, row) for row in image])
        phases = 2 * np.pi * self._freqs[:, None] * t[None, :]
        mono = (amplitudes * np.sin(phases)).sum(axis=0) / np.sqrt(cfg.rows)
        if cfg.click:
            mono += self._clicks(total)
        angle = sweep_position * np.pi / 2
        stereo = np.stack([mono * np.cos(angle), mono * np.sin(angle)], axis=1)
        return np.clip(stereo, -1.0, 1.0).astype(np.float32)

    def render_stimulus(self, stimulus: Stimulus, duration_s: float) -> np.ndarray:
        return self.render_image(stimulus_image(stimulus, self._cfg), duration_s)

    def _clicks(self, total: int) -> np.ndarray:
        click = np.zeros(total)
        length = int(_CLICK_S * self._sr)
        burst = np.hanning(length) * 0.3
        period = int(self._cfg.sweep_s * self._sr)
        for start in range(0, total, period):
            end = min(start + length, total)
            click[start:end] += burst[: end - start]
        return click
