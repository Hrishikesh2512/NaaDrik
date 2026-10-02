import dataclasses
import threading

import numpy as np
import pytest

from naadrik.capture import CameraCapture, open_camera
from naadrik.config import CameraConfig, Config
from naadrik.errors import CameraError


class FakeSource:
    def __init__(self, frames: int | None = None) -> None:
        self.remaining = frames
        self.count = 0
        self.released = threading.Event()

    def read(self) -> tuple[bool, np.ndarray | None]:
        if self.remaining is not None:
            if self.remaining <= 0:
                return False, None
            self.remaining -= 1
        self.count += 1
        image = np.full((480, 640, 3), self.count % 255, dtype=np.uint8)
        return True, image

    def release(self) -> None:
        self.released.set()


def test_frames_are_resized_rgb_and_newest_only(config: Config) -> None:
    source = FakeSource()
    capture = CameraCapture(config.camera, opener=lambda _cfg: source)
    capture.start()
    try:
        first = capture.wait_for_frame(-1, 1.0)
        assert first is not None
        assert first.image.shape == (240, 320, 3)
        later = capture.wait_for_frame(first.index + 5, 1.0)
        assert later is not None and later.index > first.index + 5
        assert later.timestamp > first.timestamp
    finally:
        capture.stop()
    assert source.released.is_set()


def test_camera_that_stops_raises(config: Config) -> None:
    capture = CameraCapture(config.camera, opener=lambda _cfg: FakeSource(frames=3))
    capture.start()
    try:
        last = capture.wait_for_frame(-1, 1.0)
        while last is not None:
            last = capture.wait_for_frame(last.index, 2.0)
        assert isinstance(capture.error, CameraError)
    finally:
        capture.stop()


def test_camera_with_no_frames_fails_start(config: Config) -> None:
    capture = CameraCapture(config.camera, opener=lambda _cfg: FakeSource(frames=0))
    with pytest.raises(CameraError, match="stopped delivering"):
        capture.start()


def test_missing_camera_has_clear_message(config: Config) -> None:
    cfg: CameraConfig = dataclasses.replace(config.camera, index=97)
    with pytest.raises(CameraError, match="--camera"):
        open_camera(cfg)
