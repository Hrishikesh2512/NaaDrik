"""Debug window: boxes, depth, colour and the sound parameters of every tracked object."""

from __future__ import annotations

import math

import cv2
import numpy as np

from naadrik.latency import END_TO_END, StageStats
from naadrik.pipeline import ObjectView, Snapshot
from naadrik.ui.qt_env import prepare_qt_environment

_SCALE = 2
_PANEL_WIDTH = 360
_FONT = cv2.FONT_HERSHEY_SIMPLEX
_WHITE = (240, 240, 240)
_GREY = (140, 140, 140)
_SOUNDING = (60, 220, 60)
_NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
_LEVEL_MARKS = {0: "-", 1: "lo", 2: "HI"}
_DISTANCE_NAMES = ("near", "mid", "far")


def note_name(freq_hz: float) -> str:
    midi = round(69 + 12 * math.log2(freq_hz / 440.0))
    return f"{_NOTE_NAMES[midi % 12]}{midi // 12 - 1}"


def distance_name(distance: float) -> str:
    return _DISTANCE_NAMES[min(int(distance * 3), 2)]


def render_debug(
    snapshot: Snapshot,
    frequencies: np.ndarray,
    colour_levels: tuple[float, float, float],
    latency: dict[str, StageStats],
    camera_fps: float,
    show_depth: bool = False,
) -> np.ndarray:
    """Compose the debug image (BGR) for one snapshot."""
    view = _base_image(snapshot, show_depth)
    for obj in snapshot.objects:
        _draw_object(view, obj)
    panel = np.full((view.shape[0], _PANEL_WIDTH, 3), 24, dtype=np.uint8)
    _draw_panel(panel, snapshot, frequencies, colour_levels, latency, camera_fps)
    return np.hstack([view, panel])


def _base_image(snapshot: Snapshot, show_depth: bool) -> np.ndarray:
    rgb = snapshot.frame.image
    height, width = rgb.shape[0] * _SCALE, rgb.shape[1] * _SCALE
    if show_depth and snapshot.disparity is not None:
        disparity = snapshot.disparity
        span = float(np.ptp(disparity)) or 1.0
        scaled = ((disparity - disparity.min()) / span * 255).astype(np.uint8)
        coloured = cv2.applyColorMap(scaled, cv2.COLORMAP_INFERNO)
        return cv2.resize(coloured, (width, height), interpolation=cv2.INTER_NEAREST)
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    return cv2.resize(bgr, (width, height), interpolation=cv2.INTER_LINEAR)


def _draw_object(image: np.ndarray, obj: ObjectView) -> None:
    h, w = image.shape[:2]
    p0 = (int(obj.box.x0 * w), int(obj.box.y0 * h))
    p1 = (int(obj.box.x1 * w), int(obj.box.y1 * h))
    sounding = obj.params is not None
    cv2.rectangle(image, p0, p1, _SOUNDING if sounding else _GREY, 3 if sounding else 1)
    swatch = tuple(int(c * 255) for c in reversed(obj.colour))
    # Keep the label inside the image when the box touches the top edge.
    top = max(p0[1], 26)
    cv2.rectangle(image, (p0[0] + 4, top - 22), (p0[0] + 22, top - 4), swatch, -1)
    label = f"#{obj.track_id} {obj.label} {obj.score:.0%}"
    if obj.distance is not None:
        label += f" d={obj.distance:.2f}"
    _text(image, label, (p0[0] + 26, top - 8), _SOUNDING if sounding else _GREY)


def _draw_panel(
    panel: np.ndarray,
    snapshot: Snapshot,
    frequencies: np.ndarray,
    colour_levels: tuple[float, float, float],
    latency: dict[str, StageStats],
    camera_fps: float,
) -> None:
    y = 24
    _text(panel, "NAADRIK  live", (12, y), _WHITE, 0.6)
    y += 30
    end_to_end = latency.get(END_TO_END)
    if end_to_end:
        _text(
            panel,
            f"capture->sound {end_to_end.mean_ms:.0f} ms (p95 {end_to_end.p95_ms:.0f})",
            (12, y),
        )
        y += 20
    for stage in ("detection", "depth", "pipeline"):
        if stage in latency:
            _text(panel, f"{stage:9} {latency[stage].mean_ms:5.0f} ms", (12, y), _GREY)
            y += 18
    _text(panel, f"camera {camera_fps:4.1f} fps", (12, y), _GREY)
    y += 30

    for obj in snapshot.objects:
        if obj.params is None:
            continue
        params = obj.params
        swatch = tuple(int(c * 255) for c in reversed(obj.colour))
        cv2.rectangle(panel, (12, y - 12), (30, y + 4), swatch, -1)
        _text(panel, f"#{obj.track_id} {obj.label}  prio {obj.priority:.2f}", (38, y), _SOUNDING)
        y += 20
        freq = float(frequencies[params.degree])
        _text(
            panel,
            f"  pitch {note_name(freq)} {freq:.0f} Hz  az {params.azimuth_deg:+.0f} deg",
            (12, y),
        )
        y += 18
        levels = "  ".join(
            f"{name} {_LEVEL_MARKS[colour_levels.index(level)]}"
            for name, level in zip(("R sitar", "G violin", "B flute"), params.levels, strict=True)
        )
        _text(
            panel,
            f"  {params.pulse_hz:.1f} Hz pulse ({distance_name(obj.sound_distance)})",
            (12, y),
        )
        y += 18
        _text(panel, f"  {levels}", (12, y))
        y += 28

    silent = sum(1 for obj in snapshot.objects if obj.params is None)
    if silent:
        _text(panel, f"{silent} more tracked, not sounding", (12, y), _GREY)
    _text(panel, "q quit  d depth  m mute", (12, panel.shape[0] - 12), _GREY)


def _text(
    image: np.ndarray,
    text: str,
    origin: tuple[int, int],
    colour: tuple[int, int, int] = _WHITE,
    scale: float = 0.45,
) -> None:
    cv2.putText(image, text, origin, _FONT, scale, (0, 0, 0), 3, cv2.LINE_AA)
    cv2.putText(image, text, origin, _FONT, scale, colour, 1, cv2.LINE_AA)


class DebugWindow:
    TITLE = "Naadrik"

    def __init__(self) -> None:
        prepare_qt_environment()
        cv2.namedWindow(self.TITLE, cv2.WINDOW_AUTOSIZE)
        self.show_depth = False

    def show(self, image: np.ndarray) -> str | None:
        """Display the image; return a command for any key pressed ('quit', 'mute')."""
        cv2.imshow(self.TITLE, image)
        key = cv2.waitKey(1) & 0xFF
        if key in (ord("q"), 27) or cv2.getWindowProperty(self.TITLE, cv2.WND_PROP_VISIBLE) < 1:
            return "quit"
        if key == ord("d"):
            self.show_depth = not self.show_depth
        if key == ord("m"):
            return "mute"
        return None

    def close(self) -> None:
        cv2.destroyWindow(self.TITLE)
