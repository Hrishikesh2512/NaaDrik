"""Rolling latency statistics per pipeline stage."""

from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass

import numpy as np

END_TO_END = "end_to_end"


@dataclass(frozen=True)
class StageStats:
    mean_ms: float
    p95_ms: float
    count: int


class LatencyMonitor:
    def __init__(self, window: int = 300) -> None:
        self._window = window
        self._samples: dict[str, deque[float]] = {}
        self._totals: dict[str, int] = {}
        self._lock = threading.Lock()

    def record(self, stage: str, seconds: float) -> None:
        with self._lock:
            if stage not in self._samples:
                self._samples[stage] = deque(maxlen=self._window)
                self._totals[stage] = 0
            self._samples[stage].append(seconds)
            self._totals[stage] += 1

    def summary(self) -> dict[str, StageStats]:
        with self._lock:
            snapshot = {stage: np.array(values) for stage, values in self._samples.items()}
            totals = dict(self._totals)
        return {
            stage: StageStats(
                float(values.mean() * 1e3), float(np.percentile(values, 95) * 1e3), totals[stage]
            )
            for stage, values in snapshot.items()
            if len(values)
        }

    def format(self) -> str:
        parts = [
            f"{stage} {stats.mean_ms:.0f} ms (p95 {stats.p95_ms:.0f})"
            for stage, stats in sorted(self.summary().items())
        ]
        return ", ".join(parts) if parts else "no measurements yet"
