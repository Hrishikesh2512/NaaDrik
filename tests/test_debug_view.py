import time

import numpy as np
import pytest

from naadrik.config import Config
from naadrik.latency import END_TO_END, StageStats
from naadrik.scene import Frame
from naadrik.sound_engine import SoundEngine
from naadrik.ui.debug_view import distance_name, note_name, render_debug
from tests.test_pipeline import make_pipeline, scene_image


@pytest.mark.parametrize(("freq", "name"), [(440.0, "A4"), (196.0, "G3"), (261.63, "C4")])
def test_note_name(freq: float, name: str) -> None:
    assert note_name(freq) == name


def test_distance_name() -> None:
    assert [distance_name(d) for d in (0.0, 0.5, 1.0)] == ["near", "mid", "far"]


@pytest.mark.parametrize("show_depth", [False, True])
def test_render_debug_composes_frame_and_panel(config: Config, show_depth: bool) -> None:
    engine = SoundEngine(config)
    pipeline, _ = make_pipeline(config, engine)
    for index in range(3):
        frame = Frame(scene_image(), index, time.perf_counter())
        pipeline.process_depth(frame)
        snapshot = pipeline.process_frame(frame)
    latency = {END_TO_END: StageStats(60.0, 70.0, 10), "detection": StageStats(25, 30, 10)}
    image = render_debug(
        snapshot, engine.bank.frequencies, config.colour.levels, latency, 30.0, show_depth
    )
    assert image.shape == (480, 640 + 360, 3)
    assert image.dtype == np.uint8
