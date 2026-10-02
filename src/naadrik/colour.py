"""Per-object colour: median RGB of the box centre after white balance and exposure correction."""

from __future__ import annotations

import numpy as np

from naadrik.config import ColourConfig
from naadrik.scene import Box

_TARGET_GREY = 0.45
_GAIN_LIMITS = (0.5, 4.0)
_GAIN_SMOOTHING = 0.1


def grey_world_gains(image: np.ndarray) -> np.ndarray:
    """Per-channel gains that bring the frame's average to a mid grey.

    This removes colour casts from the light source and also normalises exposure, so a
    dim room does not turn every object silent. Brightness is thereby judged relative to
    the scene, much as human lightness constancy does.
    """
    means = image.reshape(-1, 3).mean(axis=0) / 255.0
    return np.clip(_TARGET_GREY / np.maximum(means, 1e-3), *_GAIN_LIMITS)


class ColourSampler:
    def __init__(self, cfg: ColourConfig) -> None:
        self._cfg = cfg
        self._gains = np.ones(3)
        self._has_gains = False

    @property
    def gains(self) -> np.ndarray:
        return self._gains

    def update_white_balance(self, image: np.ndarray) -> None:
        if not self._cfg.white_balance:
            return
        gains = grey_world_gains(image)
        # Smooth across frames so auto-exposure flicker does not change object colours.
        if self._has_gains:
            gains = self._gains + _GAIN_SMOOTHING * (gains - self._gains)
        self._gains = gains
        self._has_gains = True

    def sample(self, image: np.ndarray, box: Box) -> tuple[float, float, float]:
        rows, cols = box.central(self._cfg.central_fraction).pixel_slices(*image.shape[:2])
        median = np.median(image[rows, cols].reshape(-1, 3), axis=0) / 255.0
        r, g, b = np.clip(median * self._gains, 0.0, 1.0)
        return float(r), float(g), float(b)
