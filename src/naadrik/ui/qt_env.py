"""Environment fixes for the Qt build bundled in the pip OpenCV wheels.

Those wheels ship Qt without fonts or a Wayland plugin. On import, OpenCV points
``QT_QPA_FONTDIR`` at a font folder it does not ship, and under GNOME Wayland Qt prints a
notice before falling back to X11. Qt reads both when the first window is created, so this
runs after OpenCV is imported and before ``cv2.namedWindow``.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_FONT_ROOT = Path("/usr/share/fonts")
_PREFERRED_FONT_DIRS = ("dejavu-sans-fonts", "truetype/dejavu", "adwaita-sans-fonts")


def prepare_qt_environment() -> None:
    if not sys.platform.startswith("linux"):
        return
    current = os.environ.get("QT_QPA_FONTDIR")
    if current is None or not Path(current).is_dir():
        font_dir = _find_font_dir()
        if font_dir is not None:
            os.environ["QT_QPA_FONTDIR"] = str(font_dir)
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
    if (
        os.environ.get("XDG_SESSION_TYPE") == "wayland"
        and "gnome" in desktop
        and os.environ.get("DISPLAY")
    ):
        # This Qt has no Wayland plugin and uses XWayland regardless; say so up front.
        os.environ["XDG_SESSION_TYPE"] = "x11"


def _find_font_dir() -> Path | None:
    for name in _PREFERRED_FONT_DIRS:
        candidate = _FONT_ROOT / name
        if candidate.is_dir():
            return candidate
    if _FONT_ROOT.is_dir():
        for font in _FONT_ROOT.rglob("*.ttf"):
            return font.parent
    return None
