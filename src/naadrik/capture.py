"""Webcam capture on a dedicated thread that always holds only the newest frame.

Consumers that fall behind skip frames instead of working through a backlog, which would
otherwise add latency that grows without bound.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from typing import Any

import cv2
import numpy as np

from naadrik.config import CameraConfig
from naadrik.errors import CameraError
from naadrik.scene import Frame

log = logging.getLogger(__name__)

_MAX_CONSECUTIVE_FAILURES = 30
_FIRST_FRAME_TIMEOUT_S = 5.0

VideoSource = Any  # anything with cv2.VideoCapture's read / isOpened / release / set


def resize_to_width(image: np.ndarray, width: int) -> np.ndarray:
    height = round(image.shape[0] * width / image.shape[1])
    return cv2.resize(image, (width, height), interpolation=cv2.INTER_AREA)


def open_camera(cfg: CameraConfig) -> VideoSource:
    source = cv2.VideoCapture(cfg.index)
    if not source.isOpened():
        raise CameraError(
            f"Could not open camera {cfg.index}. Check it is connected and not in use by another "
            "app, or choose another with --camera N."
        )
    source.set(cv2.CAP_PROP_FRAME_WIDTH, cfg.capture_width)
    source.set(cv2.CAP_PROP_FRAME_HEIGHT, cfg.capture_height)
    source.set(cv2.CAP_PROP_FPS, cfg.fps)
    source.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    return source


class CameraCapture:
    def __init__(
        self, cfg: CameraConfig, opener: Callable[[CameraConfig], VideoSource] = open_camera
    ) -> None:
        self._cfg = cfg
        self._opener = opener
        self._source: VideoSource = None
        self._thread: threading.Thread | None = None
        self._running = threading.Event()
        self._condition = threading.Condition()
        self._latest: Frame | None = None
        self.error: CameraError | None = None
        self.fps = 0.0

    def start(self) -> None:
        self._source = self._opener(self._cfg)
        self._running.set()
        self._thread = threading.Thread(target=self._run, name="naadrik-capture", daemon=True)
        self._thread.start()
        if self.wait_for_frame(-1, _FIRST_FRAME_TIMEOUT_S) is None:
            self.stop()
            raise self.error or CameraError(
                f"Camera {self._cfg.index} opened but sent no frames within "
                f"{_FIRST_FRAME_TIMEOUT_S:.0f} s."
            )

    def stop(self) -> None:
        self._running.clear()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        if self._source is not None:
            self._source.release()
            self._source = None

    def wait_for_frame(self, after_index: int, timeout_s: float) -> Frame | None:
        """Block until a frame newer than ``after_index`` exists; None on timeout or failure."""
        deadline = time.monotonic() + timeout_s
        with self._condition:
            while self._latest is None or self._latest.index <= after_index:
                remaining = deadline - time.monotonic()
                if remaining <= 0 or self.error is not None:
                    return None
                self._condition.wait(remaining)
            return self._latest

    def _run(self) -> None:
        failures = 0
        index = 0
        last = time.perf_counter()
        while self._running.is_set():
            ok, bgr = self._source.read()
            timestamp = time.perf_counter()
            if not ok or bgr is None:
                failures += 1
                if failures >= _MAX_CONSECUTIVE_FAILURES:
                    self._fail(CameraError(f"Camera {self._cfg.index} stopped delivering frames."))
                    return
                time.sleep(0.01)
                continue
            failures = 0
            rgb = cv2.cvtColor(resize_to_width(bgr, self._cfg.process_width), cv2.COLOR_BGR2RGB)
            self.fps += 0.1 * (1.0 / max(timestamp - last, 1e-6) - self.fps)
            last = timestamp
            with self._condition:
                self._latest = Frame(rgb, index, timestamp)
                self._condition.notify_all()
            index += 1

    def _fail(self, error: CameraError) -> None:
        log.error("%s", error)
        with self._condition:
            self.error = error
            self._condition.notify_all()
