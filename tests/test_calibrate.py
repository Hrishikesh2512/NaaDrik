import time

import numpy as np
import pytest

from naadrik.calibrate import measure_centre
from naadrik.errors import CameraError
from naadrik.scene import Frame


class FakeCamera:
    def __init__(self, frames: int) -> None:
        self.frames = frames
        self.error = None

    def wait_for_frame(self, after_index: int, _timeout: float) -> Frame | None:
        index = after_index + 1
        if index >= self.frames:
            return None
        return Frame(np.zeros((24, 32, 3), dtype=np.uint8), index, time.perf_counter())


class CentreDepth:
    def __init__(self) -> None:
        self.calls = 0

    def estimate(self, image: np.ndarray) -> np.ndarray:
        self.calls += 1
        disparity = np.ones(image.shape[:2], dtype=np.float32)
        disparity[8:16, 10:22] = 4.0 + self.calls % 2  # noisy centre reading
        return disparity


def test_measure_centre_takes_median_of_samples() -> None:
    depth = CentreDepth()
    value = measure_centre(FakeCamera(20), depth, samples=5)  # type: ignore[arg-type]
    assert depth.calls == 5
    assert value == pytest.approx(5.0)


def test_measure_centre_reports_lost_camera() -> None:
    with pytest.raises(CameraError):
        measure_centre(FakeCamera(2), CentreDepth(), samples=5)  # type: ignore[arg-type]
