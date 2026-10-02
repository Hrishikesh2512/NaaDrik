import time

import numpy as np
import pytest

from naadrik.config import Config
from naadrik.latency import LatencyMonitor
from naadrik.pipeline import LivePipeline
from naadrik.scene import Box, Detection, Frame
from naadrik.sound_engine import SoundEngine
from naadrik.sound_engine.mixer import LiveMixer


class ScriptedDetector:
    def __init__(self, detections: list[Detection]) -> None:
        self.detections = detections

    def detect(self, _image: np.ndarray) -> list[Detection]:
        return list(self.detections)


class NearLeftDepth:
    """Disparity map in which the left half of the frame is near and the right half far."""

    def estimate(self, image: np.ndarray) -> np.ndarray:
        disparity = np.ones(image.shape[:2], dtype=np.float32)
        disparity[:, : image.shape[1] // 2] = 10.0
        return disparity


class RecordingMixer(LiveMixer):
    def __init__(self, engine: SoundEngine) -> None:
        super().__init__(engine)
        self.updates: list[dict] = []

    def update(self, objects, capture_time):  # type: ignore[no-untyped-def]
        self.updates.append(dict(objects))
        super().update(objects, capture_time)


@pytest.fixture(scope="module")
def engine(config: Config) -> SoundEngine:
    return SoundEngine(config)


def scene_image() -> np.ndarray:
    image = np.full((240, 320, 3), 128, dtype=np.uint8)
    image[96:144, 32:96] = (230, 30, 30)  # red object on the left
    image[96:144, 224:288] = (30, 30, 230)  # blue object on the right
    return image


DETECTIONS = [
    Detection(Box(0.1, 0.4, 0.3, 0.6), "cup", 0.9),
    Detection(Box(0.7, 0.4, 0.9, 0.6), "bottle", 0.8),
]


def make_pipeline(config: Config, engine: SoundEngine) -> tuple[LivePipeline, RecordingMixer]:
    mixer = RecordingMixer(engine)
    pipeline = LivePipeline(
        config,
        camera=None,  # type: ignore[arg-type]  # frames are fed directly in these tests
        detector=ScriptedDetector(DETECTIONS),
        depth_model=NearLeftDepth(),
        engine=engine,
        mixer=mixer,
        monitor=LatencyMonitor(),
    )
    return pipeline, mixer


def test_pipeline_turns_detections_into_sounding_objects(
    config: Config, engine: SoundEngine
) -> None:
    pipeline, mixer = make_pipeline(config, engine)
    image = scene_image()
    for index in range(4):
        frame = Frame(image, index, time.perf_counter())
        if index % config.depth.every_n_frames == 0:
            pipeline.process_depth(frame)
        snapshot = pipeline.process_frame(frame)

    sounding = {view.label: view for view in snapshot.objects if view.params is not None}
    assert set(sounding) == {"cup", "bottle"}

    cup, bottle = sounding["cup"], sounding["bottle"]
    assert cup.sound_distance == 0.0 and bottle.sound_distance == 1.0
    assert cup.params.azimuth_deg < 0 < bottle.params.azimuth_deg
    assert cup.params.pulse_hz > bottle.params.pulse_hz
    assert cup.params.levels[0] > 0 and cup.params.levels[2] == 0  # red → pluck only
    assert bottle.params.levels[2] > 0 and bottle.params.levels[0] == 0  # blue → flute only
    assert len(mixer.updates[-1]) == 2


def test_unconfirmed_tracks_stay_silent(config: Config, engine: SoundEngine) -> None:
    pipeline, mixer = make_pipeline(config, engine)
    pipeline.process_frame(Frame(scene_image(), 0, time.perf_counter()))
    assert mixer.updates[-1] == {}


def test_pipeline_runs_without_depth(config: Config, engine: SoundEngine) -> None:
    pipeline, mixer = make_pipeline(config, engine)
    for index in range(3):
        pipeline.process_frame(Frame(scene_image(), index, time.perf_counter()))
    states = mixer.updates[-1].values()
    assert states and all(state.distance == 0.5 for state in states)
