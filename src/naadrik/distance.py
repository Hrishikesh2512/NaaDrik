"""Turn relative depth-model output into a normalised distance per object.

Depth Anything V2 predicts relative inverse depth (disparity): larger is nearer, with an
unknown scale and shift per frame. ``scene`` normalisation ranks each object against the
frame's own disparity range. ``calibrated`` uses two reference disparities recorded by
``naadrik calibrate`` (something at arm's length, something across the room).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import yaml

from naadrik.config import DepthConfig
from naadrik.errors import ConfigError
from naadrik.scene import Box

log = logging.getLogger(__name__)

_SCENE_PERCENTILES = (5.0, 95.0)


@dataclass(frozen=True)
class Calibration:
    near_disparity: float
    far_disparity: float

    def __post_init__(self) -> None:
        if not self.near_disparity > self.far_disparity:
            raise ConfigError(
                "Calibration is invalid: the near reference must have a larger disparity than "
                "the far one. Run `naadrik calibrate` again."
            )

    def save(self, path: str | Path) -> None:
        Path(path).write_text(
            yaml.safe_dump(
                {"near_disparity": self.near_disparity, "far_disparity": self.far_disparity}
            ),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: str | Path) -> Calibration:
        try:
            data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
            return cls(float(data["near_disparity"]), float(data["far_disparity"]))
        except FileNotFoundError as exc:
            raise ConfigError(
                f"Depth calibration not found at {path}. Run `naadrik calibrate` or set "
                "depth.normalisation to scene."
            ) from exc
        except (KeyError, TypeError, ValueError, yaml.YAMLError) as exc:
            raise ConfigError(f"Depth calibration file {path} is malformed: {exc}") from exc


def box_disparity(disparity: np.ndarray, box: Box, fraction: float) -> float:
    """Median disparity over the central part of the box, which is mostly the object itself."""
    rows, cols = box.central(fraction).pixel_slices(*disparity.shape)
    return float(np.median(disparity[rows, cols]))


class DistanceNormaliser:
    def __init__(self, cfg: DepthConfig, calibration: Calibration | None = None) -> None:
        if cfg.normalisation == "calibrated" and calibration is None:
            calibration = Calibration.load(cfg.calibration_path)
        self._cfg = cfg
        self._calibration = calibration if cfg.normalisation == "calibrated" else None

    def distance(self, disparity_map: np.ndarray, box: Box) -> float:
        """Normalised distance of the object in ``box``: 0 = near, 1 = far."""
        value = box_disparity(disparity_map, box, self._cfg.box_fraction)
        if self._calibration is not None:
            near, far = self._calibration.near_disparity, self._calibration.far_disparity
        else:
            far, near = np.percentile(disparity_map, _SCENE_PERCENTILES)
        if near - far <= 1e-6:
            return 0.5
        closeness = (value - far) / (near - far)
        return float(1.0 - min(max(closeness, 0.0), 1.0))


def quantise_distance(
    distance: float, previous_level: int | None, levels: int, margin: float
) -> int:
    """Quantise into ``levels`` equal bins, holding the previous level within ``margin``.

    Without hysteresis a noisy depth estimate on a bin edge would flip the pulse rate
    back and forth every frame.
    """
    level = min(int(distance * levels), levels - 1)
    if previous_level is None or level == previous_level:
        return level
    low_edge = previous_level / levels - margin
    high_edge = (previous_level + 1) / levels + margin
    return previous_level if low_edge <= distance <= high_edge else level


def level_to_distance(level: int, levels: int) -> float:
    return level / (levels - 1)
