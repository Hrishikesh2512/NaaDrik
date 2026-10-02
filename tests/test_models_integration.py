"""Runs the real models when they have been downloaded; skipped otherwise (e.g. in CI)."""

from pathlib import Path

import numpy as np
import pytest

from naadrik.config import Config


def require(path: str) -> None:
    if not Path(path).is_file():
        pytest.skip(f"model not downloaded: {path}")


def test_depth_model_output(config: Config) -> None:
    require(config.depth.model_path)
    from naadrik.depth import DepthEstimator

    estimator = DepthEstimator(config.depth)
    assert estimator.input_size(240, 320) == (252, 336)
    # A floor-like gradient: brighter, more textured at the bottom of the frame.
    rng = np.random.default_rng(0)
    image = (rng.random((240, 320, 3)) * np.linspace(40, 255, 240)[:, None, None]).astype(np.uint8)
    disparity = estimator.estimate(image)
    assert disparity.shape == (252, 336)
    assert np.all(np.isfinite(disparity))


def test_detector_runs(config: Config) -> None:
    require(config.detection.model_path)
    from naadrik.detection import ObjectDetector

    detector = ObjectDetector(config.detection)
    try:
        assert detector.detect(np.zeros((240, 320, 3), dtype=np.uint8)) == []
    finally:
        detector.close()
