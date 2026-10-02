"""Frame-to-frame object tracking so sounds glide instead of jumping between detections."""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field

from naadrik.config import TrackingConfig
from naadrik.scene import Box, Detection

_VELOCITY_SMOOTHING = 0.3


@dataclass
class Track:
    id: int
    label: str
    score: float
    box: Box
    last_seen: float
    hits: int = 1
    missed: int = 0
    velocity: tuple[float, float] = (0.0, 0.0)  # frame widths / heights per second
    distance: float | None = None
    distance_rate: float = 0.0  # distance units per second; negative = approaching
    distance_level: int | None = None
    colour: tuple[float, float, float] | None = None
    _distance_time: float | None = field(default=None, repr=False)

    @property
    def speed(self) -> float:
        return float((self.velocity[0] ** 2 + self.velocity[1] ** 2) ** 0.5)


class Tracker:
    def __init__(self, cfg: TrackingConfig) -> None:
        self._cfg = cfg
        self._tracks: list[Track] = []
        self._ids = itertools.count(1)

    @property
    def tracks(self) -> list[Track]:
        return list(self._tracks)

    def confirmed(self) -> list[Track]:
        """Tracks seen often enough to trust and seen in the latest frame."""
        return [t for t in self._tracks if t.hits >= self._cfg.min_hits and t.missed == 0]

    def update(self, detections: list[Detection], timestamp: float) -> list[Track]:
        """Associate detections with tracks by IoU (same label only); return matched tracks."""
        pairs = sorted(
            (
                (track.box.iou(det.box), ti, di)
                for ti, track in enumerate(self._tracks)
                for di, det in enumerate(detections)
                if track.label == det.label
            ),
            reverse=True,
        )
        used_tracks: set[int] = set()
        used_detections: set[int] = set()
        matched: list[Track] = []
        for iou, ti, di in pairs:
            if iou < self._cfg.iou_threshold:
                break
            if ti in used_tracks or di in used_detections:
                continue
            used_tracks.add(ti)
            used_detections.add(di)
            track = self._tracks[ti]
            self._apply(track, detections[di], timestamp)
            matched.append(track)

        for ti, track in enumerate(self._tracks):
            if ti not in used_tracks:
                track.missed += 1
        self._tracks = [t for t in self._tracks if t.missed <= self._cfg.max_missed_frames]

        for di, det in enumerate(detections):
            if di not in used_detections:
                track = Track(next(self._ids), det.label, det.score, det.box, timestamp)
                self._tracks.append(track)
                matched.append(track)
        return matched

    def update_distance(self, track: Track, distance: float, timestamp: float) -> None:
        if track.distance is None or track._distance_time is None:
            track.distance = distance
        else:
            previous = track.distance
            track.distance += self._cfg.distance_smoothing * (distance - track.distance)
            dt = timestamp - track._distance_time
            if dt > 0:
                rate = (track.distance - previous) / dt
                track.distance_rate += _VELOCITY_SMOOTHING * (rate - track.distance_rate)
        track._distance_time = timestamp

    def update_colour(self, track: Track, rgb: tuple[float, float, float]) -> None:
        if track.colour is None:
            track.colour = rgb
            return
        weight = self._cfg.colour_smoothing
        r, g, b = (old + weight * (new - old) for old, new in zip(track.colour, rgb, strict=True))
        track.colour = (r, g, b)

    def _apply(self, track: Track, det: Detection, timestamp: float) -> None:
        old_centre = track.box.centre
        track.box = track.box.blend(det.box, self._cfg.position_smoothing)
        dt = timestamp - track.last_seen
        if dt > 0:
            new_centre = track.box.centre
            vx = (new_centre[0] - old_centre[0]) / dt
            vy = (new_centre[1] - old_centre[1]) / dt
            track.velocity = (
                track.velocity[0] + _VELOCITY_SMOOTHING * (vx - track.velocity[0]),
                track.velocity[1] + _VELOCITY_SMOOTHING * (vy - track.velocity[1]),
            )
        track.score = det.score
        track.last_seen = timestamp
        track.hits += 1
        track.missed = 0
