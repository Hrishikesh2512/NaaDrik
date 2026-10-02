"""Choose which objects get a voice: closeness x importance x centredness, boosted for motion."""

from __future__ import annotations

from naadrik.config import PriorityConfig
from naadrik.tracker import Track

_UNKNOWN_DISTANCE = 0.5


def priority_score(track: Track, cfg: PriorityConfig) -> float:
    distance = track.distance if track.distance is not None else _UNKNOWN_DISTANCE
    closeness = 1.0 - min(max(distance, 0.0), 1.0)
    importance = cfg.class_importance.get(track.label, cfg.default_importance)
    offset = min(1.0, 2.0 * abs(track.box.centre[0] - 0.5))
    centredness = 1.0 - cfg.centre_weight * offset
    return closeness * importance * centredness * motion_factor(track, cfg)


def motion_factor(track: Track, cfg: PriorityConfig) -> float:
    approaching = -track.distance_rate >= cfg.approach_speed
    moving = track.speed >= cfg.moving_speed
    return 1.0 + cfg.motion_boost if approaching or moving else 1.0


class Prioritiser:
    """Keeps the selection stable: a sounding object is only replaced by a clearly better one."""

    def __init__(self, cfg: PriorityConfig, max_objects: int) -> None:
        self._cfg = cfg
        self._max = max_objects
        self._selected: list[int] = []

    def select(self, tracks: list[Track]) -> list[tuple[Track, float]]:
        scored = {t.id: (t, priority_score(t, self._cfg)) for t in tracks}
        kept = [tid for tid in self._selected if tid in scored]
        candidates = sorted(
            (tid for tid in scored if tid not in kept), key=lambda tid: -scored[tid][1]
        )
        while len(kept) < self._max and candidates:
            kept.append(candidates.pop(0))
        while candidates and kept:
            weakest = min(kept, key=lambda tid: scored[tid][1])
            best = candidates[0]
            if scored[best][1] <= scored[weakest][1] + self._cfg.switch_margin:
                break
            kept[kept.index(weakest)] = candidates.pop(0)
            candidates.append(weakest)
            candidates.sort(key=lambda tid: -scored[tid][1])
        kept.sort(key=lambda tid: -scored[tid][1])
        self._selected = kept
        return [scored[tid] for tid in kept]
