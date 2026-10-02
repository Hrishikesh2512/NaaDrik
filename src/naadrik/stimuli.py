"""Synthetic stimuli on a 3 x 3 x 3 grid (side x height x distance) with a set of colours."""

from __future__ import annotations

import itertools
import random
from dataclasses import dataclass

from naadrik.sound_engine import ObjectState

SIDES = {"left": 1 / 6, "centre": 0.5, "right": 5 / 6}
HEIGHTS = {"high": 1 / 6, "middle": 0.5, "low": 5 / 6}
DISTANCES = {"near": 0.0, "mid": 0.5, "far": 1.0}
COLOURS: dict[str, tuple[float, float, float]] = {
    "red": (1.0, 0.0, 0.0),
    "green": (0.0, 1.0, 0.0),
    "blue": (0.0, 0.0, 1.0),
    "yellow": (1.0, 1.0, 0.0),
    "cyan": (0.0, 1.0, 1.0),
    "magenta": (1.0, 0.0, 1.0),
    "white": (1.0, 1.0, 1.0),
}
AXES = ("side", "height", "distance", "colour")
OPTIONS: dict[str, tuple[str, ...]] = {
    "side": tuple(SIDES),
    "height": tuple(HEIGHTS),
    "distance": tuple(DISTANCES),
    "colour": tuple(COLOURS),
}


@dataclass(frozen=True)
class Stimulus:
    side: str
    height: str
    distance: str
    colour: str

    def state(self) -> ObjectState:
        r, g, b = COLOURS[self.colour]
        return ObjectState(
            SIDES[self.side], HEIGHTS[self.height], DISTANCES[self.distance], r, g, b
        )

    def value(self, axis: str) -> str:
        return str(getattr(self, axis))


def full_grid(colours: tuple[str, ...] = tuple(COLOURS)) -> list[Stimulus]:
    return [
        Stimulus(side, height, distance, colour)
        for side, height, distance, colour in itertools.product(SIDES, HEIGHTS, DISTANCES, colours)
    ]


def sample(
    count: int, rng: random.Random, colours: tuple[str, ...] = tuple(COLOURS)
) -> list[Stimulus]:
    """``count`` stimuli that cover the grid as evenly as possible, in random order."""
    grid = full_grid(colours)
    chosen: list[Stimulus] = []
    while len(chosen) < count:
        rng.shuffle(grid)
        chosen.extend(grid[: count - len(chosen)])
    return chosen
