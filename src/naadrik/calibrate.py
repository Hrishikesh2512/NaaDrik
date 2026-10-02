"""``naadrik calibrate``: record near and far reference disparities for the depth model."""

from __future__ import annotations

import logging
from collections.abc import Callable

import numpy as np

from naadrik.capture import CameraCapture
from naadrik.config import Config
from naadrik.depth import DepthEstimator
from naadrik.distance import Calibration, box_disparity
from naadrik.errors import CameraError
from naadrik.scene import Box

log = logging.getLogger(__name__)

_CENTRE = Box(0.35, 0.35, 0.65, 0.65)
_SAMPLES = 8

STEPS = (
    (
        "near",
        "Hold a large object (a book or your hand) about 50 cm in front of the camera, "
        "filling the centre of the view.",
    ),
    ("far", "Point the camera at a wall or large object about 3 metres away."),
)


def measure_centre(camera: CameraCapture, depth: DepthEstimator, samples: int = _SAMPLES) -> float:
    values = []
    index = -1
    for _ in range(samples):
        frame = camera.wait_for_frame(index, 2.0)
        if frame is None:
            raise camera.error or CameraError("Camera stopped delivering frames.")
        index = frame.index
        values.append(box_disparity(depth.estimate(frame.image), _CENTRE, 1.0))
    return float(np.median(values))


def run_calibration(config: Config, ask: Callable[[str], str] = input) -> Calibration:
    depth = DepthEstimator(config.depth)
    camera = CameraCapture(config.camera)
    camera.start()
    try:
        readings = {}
        for name, instruction in STEPS:
            ask(f"\n{instruction}\nPress Enter when ready... ")
            readings[name] = measure_centre(camera, depth)
            print(f"  {name} reference disparity: {readings[name]:.3f}")
    finally:
        camera.stop()
    calibration = Calibration(readings["near"], readings["far"])
    calibration.save(config.depth.calibration_path)
    print(
        f"\nSaved {config.depth.calibration_path}. Set depth.normalisation to 'calibrated' "
        "in config.yaml to use it."
    )
    return calibration
