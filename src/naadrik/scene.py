"""Types shared by the perception modules. Coordinates are normalised to [0, 1], origin top-left."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Box:
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def centre(self) -> tuple[float, float]:
        return (self.x0 + self.x1) / 2.0, (self.y0 + self.y1) / 2.0

    @property
    def width(self) -> float:
        return max(0.0, self.x1 - self.x0)

    @property
    def height(self) -> float:
        return max(0.0, self.y1 - self.y0)

    @property
    def area(self) -> float:
        return self.width * self.height

    def iou(self, other: Box) -> float:
        ix = max(0.0, min(self.x1, other.x1) - max(self.x0, other.x0))
        iy = max(0.0, min(self.y1, other.y1) - max(self.y0, other.y0))
        inter = ix * iy
        union = self.area + other.area - inter
        return inter / union if union > 0 else 0.0

    def central(self, fraction: float) -> Box:
        cx, cy = self.centre
        half_w, half_h = self.width * fraction / 2.0, self.height * fraction / 2.0
        return Box(cx - half_w, cy - half_h, cx + half_w, cy + half_h)

    def blend(self, other: Box, weight: float) -> Box:
        """Move ``weight`` of the way towards ``other``."""
        keep = 1.0 - weight
        return Box(
            self.x0 * keep + other.x0 * weight,
            self.y0 * keep + other.y0 * weight,
            self.x1 * keep + other.x1 * weight,
            self.y1 * keep + other.y1 * weight,
        )

    def pixel_slices(self, height: int, width: int) -> tuple[slice, slice]:
        """Row and column slices covering the box; never empty."""
        x0 = min(max(int(self.x0 * width), 0), width - 1)
        y0 = min(max(int(self.y0 * height), 0), height - 1)
        x1 = min(max(int(np.ceil(self.x1 * width)), x0 + 1), width)
        y1 = min(max(int(np.ceil(self.y1 * height)), y0 + 1), height)
        return slice(y0, y1), slice(x0, x1)


@dataclass(frozen=True)
class Detection:
    box: Box
    label: str
    score: float


@dataclass(frozen=True)
class Frame:
    image: np.ndarray  # RGB uint8, already resized for processing
    index: int
    timestamp: float  # time.perf_counter() when the frame reached the app
