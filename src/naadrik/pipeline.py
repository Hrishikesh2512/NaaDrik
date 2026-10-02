"""Live pipeline: camera → detection + depth → tracking → prioritisation → live mixer.

Threads: capture (in ``CameraCapture``), detection (this module), depth (this module) and the
audio callback (PortAudio). Detection drives the sound at camera rate; depth runs every Nth
frame and its latest map is reused in between.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Protocol

import numpy as np

from naadrik.capture import CameraCapture
from naadrik.colour import ColourSampler
from naadrik.config import Config
from naadrik.distance import DistanceNormaliser, level_to_distance, quantise_distance
from naadrik.latency import LatencyMonitor
from naadrik.prioritiser import Prioritiser
from naadrik.scene import Box, Detection, Frame
from naadrik.sound_engine import ObjectState, SoundEngine, SoundParams
from naadrik.sound_engine.mixer import LiveMixer
from naadrik.tracker import Track, Tracker

log = logging.getLogger(__name__)

_FRAME_WAIT_S = 1.0
_UNKNOWN_DISTANCE = 0.5
_NEUTRAL_COLOUR = (0.5, 0.5, 0.5)


class Detector(Protocol):
    def detect(self, image_rgb: np.ndarray) -> list[Detection]: ...


class DepthModel(Protocol):
    def estimate(self, image_rgb: np.ndarray) -> np.ndarray: ...


@dataclass(frozen=True)
class ObjectView:
    """What the debug view shows for one tracked object."""

    track_id: int
    label: str
    score: float
    box: Box
    distance: float | None
    sound_distance: float
    colour: tuple[float, float, float]
    priority: float
    params: SoundParams | None  # None when the object is tracked but not sounding


@dataclass(frozen=True)
class Snapshot:
    frame: Frame
    objects: tuple[ObjectView, ...]
    disparity: np.ndarray | None


class LivePipeline:
    def __init__(
        self,
        config: Config,
        camera: CameraCapture,
        detector: Detector,
        depth_model: DepthModel,
        engine: SoundEngine,
        mixer: LiveMixer,
        monitor: LatencyMonitor,
        normaliser: DistanceNormaliser | None = None,
    ) -> None:
        self._config = config
        self._camera = camera
        self._detector = detector
        self._depth_model = depth_model
        self._engine = engine
        self._mixer = mixer
        self._monitor = monitor
        self._normaliser = normaliser or DistanceNormaliser(config.depth)
        self._tracker = Tracker(config.tracking)
        self._prioritiser = Prioritiser(config.priority, config.objects.max_objects)
        self._colour = ColourSampler(config.colour)
        self._running = threading.Event()
        self._threads: list[threading.Thread] = []
        self._lock = threading.Lock()
        self._disparity: tuple[np.ndarray, int] | None = None
        self._disparity_used = -1
        self._snapshot: Snapshot | None = None
        self.error: BaseException | None = None

    @property
    def snapshot(self) -> Snapshot | None:
        return self._snapshot

    def start(self) -> None:
        self._running.set()
        for name, target in (("detection", self._detection_loop), ("depth", self._depth_loop)):
            thread = threading.Thread(target=self._guard(target), name=f"naadrik-{name}")
            thread.daemon = True
            thread.start()
            self._threads.append(thread)

    def stop(self) -> None:
        self._running.clear()
        for thread in self._threads:
            thread.join(timeout=3.0)
        self._threads.clear()
        self._mixer.update({}, time.perf_counter())

    @property
    def running(self) -> bool:
        return self._running.is_set() and self.error is None

    def _guard(self, loop):  # type: ignore[no-untyped-def]
        def run() -> None:
            try:
                loop()
            except BaseException as exc:
                log.exception("pipeline thread failed")
                self.error = exc
                self._running.clear()

        return run

    def _detection_loop(self) -> None:
        last_index = -1
        while self._running.is_set():
            frame = self._camera.wait_for_frame(last_index, _FRAME_WAIT_S)
            if frame is None:
                if self._camera.error is not None:
                    raise self._camera.error
                continue
            last_index = frame.index
            self.process_frame(frame)

    def _depth_loop(self) -> None:
        every = self._config.depth.every_n_frames
        last_index = -every
        while self._running.is_set():
            frame = self._camera.wait_for_frame(last_index + every - 1, _FRAME_WAIT_S)
            if frame is None:
                if self._camera.error is not None:
                    return
                continue
            self.process_depth(frame)
            last_index = frame.index

    def process_depth(self, frame: Frame) -> None:
        started = time.perf_counter()
        disparity = self._depth_model.estimate(frame.image)
        self._monitor.record("depth", time.perf_counter() - started)
        with self._lock:
            self._disparity = (disparity, frame.index)

    def process_frame(self, frame: Frame) -> Snapshot:
        started = time.perf_counter()
        self._colour.update_white_balance(frame.image)
        detections = self._detector.detect(frame.image)
        self._monitor.record("detection", time.perf_counter() - started)

        matched = self._tracker.update(detections, frame.timestamp)
        disparity = self._update_distances(matched, frame.timestamp)
        for track in matched:
            self._tracker.update_colour(track, self._colour.sample(frame.image, track.box))

        selected = self._prioritiser.select(self._tracker.confirmed())
        states = {track.id: self._object_state(track) for track, _ in selected}
        self._mixer.update(states, frame.timestamp)
        self._monitor.record("pipeline", time.perf_counter() - frame.timestamp)

        snapshot = self._build_snapshot(frame, selected, states, disparity)
        self._snapshot = snapshot
        return snapshot

    def _update_distances(self, matched: list[Track], timestamp: float) -> np.ndarray | None:
        with self._lock:
            latest = self._disparity
        if latest is None:
            return None
        disparity, index = latest
        fresh_map = index != self._disparity_used
        self._disparity_used = index
        levels = self._config.depth.levels
        for track in matched:
            # Only feed a distance when the map is new (or the track has none yet), so the
            # approach rate reflects real change rather than the same map read repeatedly.
            if fresh_map or track.distance is None:
                self._tracker.update_distance(
                    track, self._normaliser.distance(disparity, track.box), timestamp
                )
            if levels and track.distance is not None:
                track.distance_level = quantise_distance(
                    track.distance, track.distance_level, levels, self._config.depth.hysteresis
                )
        return disparity

    def _sound_distance(self, track: Track) -> float:
        levels = self._config.depth.levels
        if levels and track.distance_level is not None:
            return level_to_distance(track.distance_level, levels)
        return track.distance if track.distance is not None else _UNKNOWN_DISTANCE

    def _object_state(self, track: Track) -> ObjectState:
        cx, cy = track.box.centre
        r, g, b = track.colour or _NEUTRAL_COLOUR
        return ObjectState(cx, cy, self._sound_distance(track), r, g, b)

    def _build_snapshot(
        self,
        frame: Frame,
        selected: list[tuple[Track, float]],
        states: dict[int, ObjectState],
        disparity: np.ndarray | None,
    ) -> Snapshot:
        scores = {track.id: score for track, score in selected}
        views = []
        for track in self._tracker.tracks:
            if track.missed:
                continue
            state = states.get(track.id)
            views.append(
                ObjectView(
                    track_id=track.id,
                    label=track.label,
                    score=track.score,
                    box=track.box,
                    distance=track.distance,
                    sound_distance=self._sound_distance(track),
                    colour=track.colour or _NEUTRAL_COLOUR,
                    priority=scores.get(track.id, 0.0),
                    params=self._engine.map(state) if state is not None else None,
                )
            )
        views.sort(key=lambda view: (view.params is None, -view.priority))
        return Snapshot(frame, tuple(views), disparity)
