"""Short spoken descriptions such as "red cup, left, near"."""

from __future__ import annotations

from naadrik.config import Config
from naadrik.sound_engine import ObjectState
from naadrik.sound_engine.mapping import quantise_channel

# Names for every combination of quantised (red, green, blue) levels: 0 off, 1 low, 2 high.
COLOUR_NAMES: dict[tuple[int, int, int], str] = {
    (0, 0, 0): "black",
    (1, 1, 1): "grey",
    (2, 2, 2): "white",
    (2, 0, 0): "red",
    (1, 0, 0): "dark red",
    (0, 2, 0): "green",
    (0, 1, 0): "dark green",
    (0, 0, 2): "blue",
    (0, 0, 1): "dark blue",
    (2, 2, 0): "yellow",
    (1, 1, 0): "olive",
    (0, 2, 2): "cyan",
    (0, 1, 1): "teal",
    (2, 0, 2): "magenta",
    (1, 0, 1): "purple",
    (2, 1, 0): "orange",
    (1, 2, 0): "lime",
    (2, 0, 1): "rose",
    (1, 0, 2): "violet",
    (0, 2, 1): "spring green",
    (0, 1, 2): "sky blue",
    (2, 1, 1): "pink",
    (1, 2, 1): "light green",
    (1, 1, 2): "light blue",
    (2, 2, 1): "cream",
    (2, 1, 2): "orchid",
    (1, 2, 2): "pale cyan",
}

_SIDES = ("left", "centre", "right")
_HEIGHTS = ("high", "middle", "low")
_DISTANCES = ("near", "mid distance", "far")


def colour_name(r: float, g: float, b: float, config: Config) -> str:
    key = tuple(quantise_channel(channel, config.colour) for channel in (r, g, b))
    return COLOUR_NAMES[key]  # type: ignore[index]


def _third(value: float, names: tuple[str, str, str]) -> str:
    return names[min(int(min(max(value, 0.0), 1.0) * 3), 2)]


def describe(label: str, state: ObjectState, config: Config) -> str:
    parts = [
        f"{colour_name(state.r, state.g, state.b, config)} {label}",
        _third(state.x, _SIDES),
    ]
    if config.training.include_height:
        parts.append(_third(state.y, _HEIGHTS))
    parts.append(_third(state.distance, _DISTANCES))
    return ", ".join(parts)
