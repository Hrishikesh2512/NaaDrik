"""``naadrik live``: wire camera, models, pipeline, audio and the debug window together."""

from __future__ import annotations

import dataclasses
import logging
import time
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from naadrik.audio_output import AudioOutput
from naadrik.capture import CameraCapture
from naadrik.config import Config
from naadrik.depth import DepthEstimator
from naadrik.detection import ObjectDetector
from naadrik.latency import END_TO_END, LatencyMonitor
from naadrik.pipeline import LivePipeline
from naadrik.sound_engine import SoundEngine
from naadrik.sound_engine.mixer import LiveMixer
from naadrik.training.coach import TrainingCoach
from naadrik.ui.debug_view import DebugWindow, render_debug

log = logging.getLogger(__name__)

_REPORT_EVERY_S = 5.0
_SAVE_EVERY_S = 1.0
_IDLE_SLEEP_S = 0.03


@dataclass(frozen=True)
class LiveOptions:
    camera_index: int | None = None
    device: str | int | None = None
    show_window: bool = True
    duration_s: float | None = None
    save_debug: Path | None = None
    muted: bool = False
    coach: TrainingCoach | None = None


class LiveSession:
    def __init__(self, config: Config, options: LiveOptions) -> None:
        if options.camera_index is not None:
            camera_cfg = dataclasses.replace(config.camera, index=options.camera_index)
            config = dataclasses.replace(config, camera=camera_cfg)
        self.config = config
        self.options = options
        self.monitor = LatencyMonitor()
        log.info("loading sound engine and models")
        self.engine = SoundEngine(config)
        self.detector = ObjectDetector(config.detection)
        self.depth = DepthEstimator(config.depth)
        self.camera = CameraCapture(config.camera)
        training = config.training
        self.mixer = LiveMixer(
            self.engine,
            on_applied=self._record_end_to_end,
            duck_db=training.duck_db if options.coach else 0.0,
            gap_s=training.gap_s if options.coach else 0.0,
            spatialise_speech=training.spatialise_speech,
        )
        self.mixer.muted = options.muted
        device = options.device if options.device is not None else config.audio.device
        self.audio = AudioOutput(
            self.mixer.render,
            config.audio.sample_rate,
            config.audio.block_size,
            device,
            latency=config.audio.live_latency_s,
        )
        self.pipeline = LivePipeline(
            config,
            self.camera,
            self.detector,
            self.depth,
            self.engine,
            self.mixer,
            self.monitor,
            coach=options.coach,
        )
        self.window: DebugWindow | None = None

    def run(self) -> LatencyMonitor:
        try:
            self.camera.start()
            self.audio.start()
            self.pipeline.start()
            log.info(
                "live: audio buffer %.0f ms; press q in the window or Ctrl-C to stop",
                self.audio.latency_s * 1e3,
            )
            if self.options.show_window:
                self.window = DebugWindow()
            self._loop()
        finally:
            self._shutdown()
        log.info("latency: %s", self.monitor.format())
        return self.monitor

    def _record_end_to_end(self, capture_time: float) -> None:
        # Runs on the audio thread when it applies a frame's update; the remaining time
        # before the DAC plays this block is added to get capture-to-sound latency.
        elapsed = time.perf_counter() - capture_time
        self.monitor.record(END_TO_END, elapsed + self.audio.output_delay_s)

    def _loop(self) -> None:
        started = last_report = time.monotonic()
        last_saved = 0.0
        while self.pipeline.running:
            now = time.monotonic()
            if self.options.duration_s is not None and now - started >= self.options.duration_s:
                break
            if self.audio.error is not None:
                raise self.audio.error
            if self._wants_image() and self.pipeline.snapshot is not None:
                image = self._render()
                if self.options.save_debug is not None and now - last_saved >= _SAVE_EVERY_S:
                    cv2.imwrite(str(self.options.save_debug), image)
                    last_saved = now
                if self.window is not None and not self._handle(self.window.show(image)):
                    break
            if now - last_report >= _REPORT_EVERY_S:
                self._report()
                last_report = now
            if self.window is None:
                time.sleep(_IDLE_SLEEP_S)
        if self.pipeline.error is not None:
            raise self.pipeline.error

    def _wants_image(self) -> bool:
        return self.window is not None or self.options.save_debug is not None

    def _render(self) -> np.ndarray:
        snapshot = self.pipeline.snapshot
        assert snapshot is not None
        return render_debug(
            snapshot,
            self.engine.bank.frequencies,
            self.config.colour.levels,
            self.monitor.summary(),
            self.camera.fps,
            show_depth=self.window.show_depth if self.window is not None else False,
        )

    def _handle(self, command: str | None) -> bool:
        """Apply a window command; False means stop."""
        if command == "quit":
            return False
        if command == "mute":
            self.mixer.muted = not self.mixer.muted
            log.info("sound %s", "muted" if self.mixer.muted else "on")
        return True

    def _report(self) -> None:
        snapshot = self.pipeline.snapshot
        sounding = sum(1 for o in snapshot.objects if o.params) if snapshot else 0
        log.info(
            "camera %.1f fps, %d sounding, %d underflows; %s",
            self.camera.fps,
            sounding,
            self.audio.underflows,
            self.monitor.format(),
        )

    def _shutdown(self) -> None:
        self.pipeline.stop()
        log.info("audio underflows: %d", self.audio.underflows)
        self.audio.stop()
        self.camera.stop()
        self.detector.close()
        if self.window is not None:
            self.window.close()
