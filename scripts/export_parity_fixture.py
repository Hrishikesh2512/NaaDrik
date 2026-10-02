"""Export reference values from the Python engine for the Android (Kotlin) parity tests.

Run after changing any mapping:  python scripts/export_parity_fixture.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

from naadrik.config import load_config
from naadrik.distance import quantise_distance
from naadrik.prioritiser import motion_factor, priority_score
from naadrik.scene import Box
from naadrik.sound_engine import soft_clip
from naadrik.sound_engine.mapping import (
    distance_to_pulse_rate,
    height_to_degree,
    quantise_channel,
    rgb_to_levels,
    scale_frequencies,
    x_to_azimuth,
)
from naadrik.spatialiser import ear_alphas, head_shadow_coefficients, interaural_time_difference
from naadrik.stimuli import full_grid
from naadrik.tracker import Track
from naadrik.training.describe import COLOUR_NAMES, describe
from naadrik.training.progress import speech_probability

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "android" / "core" / "src" / "test" / "resources" / "parity.json"


def build_fixture() -> dict:
    config = load_config(ROOT / "config.yaml")
    n = len(scale_frequencies(config.pitch))
    values = [-0.5, 0.0, 0.1, 0.2499, 0.25, 0.3, 0.5, 0.59, 0.6, 0.75, 0.99, 1.0, 1.7]
    azimuths = [-170.0, -120.0, -90.0, -45.0, -10.0, 0.0, 10.0, 45.0, 80.0, 90.0, 135.0, 180.0]
    rgbs = [(r, g, b) for r in (0.0, 0.4, 1.0) for g in (0.0, 0.4, 1.0) for b in (0.0, 0.4, 1.0)]
    sr = config.audio.sample_rate
    tracks = [
        ("person", 0.5, 0.2, 0.0, 0.0),
        ("cup", 0.05, 0.6, 0.0, 0.0),
        ("car", 0.7, 0.5, -0.5, 0.0),
        ("kite", 0.3, None, 0.0, 0.4),
    ]
    return {
        "scale_frequencies": scale_frequencies(config.pitch).tolist(),
        "height_to_degree": [[y, height_to_degree(y, n)] for y in values],
        "distance_to_pulse_rate": [[d, distance_to_pulse_rate(d, config.pulse)] for d in values],
        "quantise_channel": [[v, quantise_channel(v, config.colour)] for v in values],
        "rgb_to_levels": [[list(rgb), list(rgb_to_levels(*rgb, config.colour))] for rgb in rgbs],
        "x_to_azimuth": [[x, x_to_azimuth(x, config.spatial)] for x in values],
        "itd": [[a, interaural_time_difference(a, config.spatial.head_radius_m)] for a in azimuths],
        "ear_alphas": [[a, list(ear_alphas(a))] for a in azimuths],
        "head_shadow": [
            [alpha, *(c.tolist() for c in head_shadow_coefficients(alpha, 0.0875, sr))]
            for alpha in (0.1, 0.5, 1.0, 1.5, 2.0)
        ],
        "soft_clip": [
            [x, float(soft_clip(np.array([x]))[0])]
            for x in (-5.0, -0.9, -0.5, 0.0, 0.79, 0.8, 0.95, 3.0)
        ],
        "colour_names": [[list(key), name] for key, name in COLOUR_NAMES.items()],
        "describe": [
            [s.side, s.height, s.distance, s.colour, describe("cup", s.state(), config)]
            for s in full_grid()[::17]
        ],
        "quantise_distance": [
            [d, prev, quantise_distance(d, prev, 3, config.depth.hysteresis)]
            for d in (0.0, 0.3, 0.36, 0.42, 0.5, 0.62, 0.7, 1.0)
            for prev in (None, 0, 1, 2)
        ],
        "speech_probability": [[s, speech_probability(s, config.training)] for s in range(1, 12)],
        "priority": [
            [
                label,
                x,
                distance,
                rate,
                speed,
                priority_score(_track(label, x, distance, rate, speed), config.priority),
                motion_factor(_track(label, x, distance, rate, speed), config.priority),
            ]
            for label, x, distance, rate, speed in tracks
        ],
    }


def _track(label: str, x: float, distance: float | None, rate: float, speed: float) -> Track:
    box = Box(x - 0.05, 0.4, x + 0.05, 0.5)
    return Track(
        1, label, 0.9, box, 0.0, velocity=(speed, 0.0), distance=distance, distance_rate=rate
    )


def main() -> int:
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE.write_text(json.dumps(build_fixture(), indent=1) + "\n", encoding="utf-8")
    print(f"wrote {FIXTURE.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
