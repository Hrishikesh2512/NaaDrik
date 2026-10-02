"""Listening demo: example objects that show off each mapping so they can be heard and tuned."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from naadrik.sound_engine import ObjectState

Path = Callable[[float], ObjectState]


@dataclass(frozen=True)
class Scenario:
    name: str
    description: str
    paths: tuple[Path, ...]
    duration_s: float = 3.0


def _still(x: float, y: float, distance: float, r: float, g: float, b: float) -> Path:
    state = ObjectState(x, y, distance, r, g, b)
    return lambda _t: state


def _moving(duration_s: float, start: ObjectState, end: ObjectState) -> Path:
    def path(t: float) -> ObjectState:
        k = min(max(t / duration_s, 0.0), 1.0)
        return ObjectState(
            *(
                a + (b - a) * k
                for a, b in zip(vars(start).values(), vars(end).values(), strict=True)
            )
        )

    return path


SCENARIOS: tuple[Scenario, ...] = (
    Scenario(
        "red-high-left-close",
        "Red object, high, on the left, close: fast sitar plucks, high pitch, left ear.",
        (_still(0.1, 0.1, 0.0, 1.0, 0.0, 0.0),),
    ),
    Scenario(
        "blue-low-right-far",
        "Blue object, low, on the right, far: slow low flute notes, right ear.",
        (_still(0.9, 0.9, 1.0, 0.0, 0.0, 1.0),),
        duration_s=4.0,
    ),
    Scenario(
        "green-centre-mid",
        "Green object, centre, mid distance: violin in the middle at a medium pulse.",
        (_still(0.5, 0.5, 0.5, 0.0, 1.0, 0.0),),
    ),
    Scenario(
        "yellow",
        "Yellow (red + green): sitar and violin together.",
        (_still(0.35, 0.4, 0.35, 1.0, 0.9, 0.1),),
    ),
    Scenario(
        "cyan",
        "Cyan (green + blue): violin and flute together.",
        (_still(0.65, 0.4, 0.35, 0.1, 0.9, 0.9),),
    ),
    Scenario(
        "magenta",
        "Magenta (red + blue): sitar and flute together.",
        (_still(0.5, 0.4, 0.35, 0.9, 0.1, 0.9),),
    ),
    Scenario(
        "orange",
        "Orange: loud sitar with a quiet violin (green quantised to 'low').",
        (_still(0.5, 0.4, 0.35, 1.0, 0.5, 0.0),),
    ),
    Scenario(
        "dark-red-vs-red",
        "Brightness: dark red (quiet sitar) on the left, bright red (loud sitar) on the right.",
        (_still(0.1, 0.5, 0.4, 0.45, 0.0, 0.0), _still(0.9, 0.5, 0.4, 1.0, 0.0, 0.0)),
    ),
    Scenario(
        "grey-vs-white",
        "Brightness: grey (all three quiet) on the left, white (all three loud) on the right.",
        (_still(0.1, 0.5, 0.4, 0.45, 0.45, 0.45), _still(0.9, 0.5, 0.4, 1.0, 1.0, 1.0)),
    ),
    Scenario(
        "black-vs-white",
        "Presence: black (soft hum only) on the left, white (hum + all three loud) on the right.",
        (_still(0.1, 0.5, 0.2, 0.0, 0.0, 0.0), _still(0.9, 0.5, 0.2, 1.0, 1.0, 1.0)),
    ),
    Scenario(
        "black",
        "Black object: no colour instruments, only the presence hum, still pulsing and placed.",
        (_still(0.5, 0.5, 0.0, 0.0, 0.0, 0.0),),
        duration_s=1.5,
    ),
    Scenario(
        "height-sweep",
        "Height: a flute moving from the bottom of the frame to the top climbs the scale.",
        (_moving(5.0, ObjectState(0.5, 1.0, 0.0, 0, 0, 1), ObjectState(0.5, 0.0, 0.0, 0, 0, 1)),),
        duration_s=5.0,
    ),
    Scenario(
        "pan-sweep",
        "Position: a violin gliding from far left to far right.",
        (_moving(5.0, ObjectState(0.0, 0.5, 0.2, 0, 1, 0), ObjectState(1.0, 0.5, 0.2, 0, 1, 0)),),
        duration_s=5.0,
    ),
    Scenario(
        "approach",
        "Distance: a sitar approaching from far to close; the pulse speeds up, volume stays put.",
        (_moving(6.0, ObjectState(0.5, 0.4, 1.0, 1, 0, 0), ObjectState(0.5, 0.4, 0.0, 1, 0, 0)),),
        duration_s=6.0,
    ),
    Scenario(
        "three-objects",
        "Scene: red high-left close, green centre mid, blue low-right far, all at once.",
        (
            _still(0.15, 0.2, 0.1, 1.0, 0.0, 0.0),
            _still(0.5, 0.5, 0.5, 0.0, 1.0, 0.0),
            _still(0.85, 0.8, 0.9, 0.0, 0.0, 1.0),
        ),
        duration_s=5.0,
    ),
)


def scenario_names() -> list[str]:
    return [scenario.name for scenario in SCENARIOS]


def find_scenario(name: str) -> Scenario:
    for scenario in SCENARIOS:
        if scenario.name == name:
            return scenario
    raise KeyError(name)
