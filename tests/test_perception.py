import dataclasses
from pathlib import Path

import numpy as np
import pytest

from naadrik.colour import ColourSampler, grey_world_gains
from naadrik.config import Config
from naadrik.distance import (
    Calibration,
    DistanceNormaliser,
    box_disparity,
    level_to_distance,
    quantise_distance,
)
from naadrik.errors import ConfigError
from naadrik.prioritiser import Prioritiser, priority_score
from naadrik.scene import Box, Detection
from naadrik.tracker import Track, Tracker

# --- Box -------------------------------------------------------------------------------


def test_box_geometry() -> None:
    box = Box(0.2, 0.2, 0.6, 0.4)
    assert box.centre == pytest.approx((0.4, 0.3))
    assert box.area == pytest.approx(0.08)
    assert box.iou(box) == pytest.approx(1.0)
    assert box.iou(Box(0.7, 0.7, 0.9, 0.9)) == 0.0
    assert vars(box.central(0.5)) == pytest.approx(vars(Box(0.3, 0.25, 0.5, 0.35)))


def test_pixel_slices_never_empty() -> None:
    rows, cols = Box(0.999, 0.999, 1.0, 1.0).pixel_slices(10, 10)
    assert rows.stop > rows.start and cols.stop > cols.start


# --- Colour ----------------------------------------------------------------------------


def make_scene(background: tuple[int, int, int], patch: tuple[int, int, int]) -> np.ndarray:
    image = np.full((100, 100, 3), background, dtype=np.uint8)
    image[40:60, 40:60] = patch
    return image


def test_sample_uses_box_centre_not_background(config: Config) -> None:
    cfg = dataclasses.replace(config.colour, white_balance=False)
    image = make_scene((0, 0, 0), (255, 0, 0))
    # Box twice the patch size: half its area is background, but the centre is all red.
    r, g, b = ColourSampler(cfg).sample(image, Box(0.3, 0.3, 0.7, 0.7))
    assert (r, g, b) == pytest.approx((1.0, 0.0, 0.0))


def test_white_balance_removes_colour_cast() -> None:
    warm = np.zeros((10, 10, 3), dtype=np.uint8)
    warm[...] = (160, 120, 80)
    gains = grey_world_gains(warm)
    balanced = warm[0, 0] / 255.0 * gains
    assert np.ptp(balanced) == pytest.approx(0.0, abs=1e-6)


def test_white_balance_lifts_dim_scene(config: Config) -> None:
    sampler = ColourSampler(config.colour)
    image = make_scene((20, 20, 20), (60, 20, 20))
    sampler.update_white_balance(image)
    r, g, _ = sampler.sample(image, Box(0.45, 0.45, 0.55, 0.55))
    assert r > config.colour.thresholds[1]
    assert g < config.colour.thresholds[1]


# --- Distance --------------------------------------------------------------------------


def disparity_map() -> np.ndarray:
    disparity = np.full((100, 100), 1.0, dtype=np.float32)  # far background
    disparity[10:40, 10:40] = 10.0  # near object, top-left
    disparity[60:90, 60:90] = 5.0  # mid object, bottom-right
    return disparity


def test_box_disparity_is_median_of_centre() -> None:
    assert box_disparity(disparity_map(), Box(0.05, 0.05, 0.45, 0.45), 0.6) == pytest.approx(10.0)


def test_scene_normalisation_orders_objects(config: Config) -> None:
    normaliser = DistanceNormaliser(dataclasses.replace(config.depth, normalisation="scene"))
    disparity = disparity_map()
    near = normaliser.distance(disparity, Box(0.1, 0.1, 0.4, 0.4))
    mid = normaliser.distance(disparity, Box(0.6, 0.6, 0.9, 0.9))
    far = normaliser.distance(disparity, Box(0.45, 0.0, 0.55, 0.1))
    assert near == pytest.approx(0.0)
    assert far == pytest.approx(1.0)
    assert near < mid < far


def test_calibrated_normalisation(config: Config, tmp_path: Path) -> None:
    path = tmp_path / "calibration.yaml"
    Calibration(near_disparity=10.0, far_disparity=2.0).save(path)
    cfg = dataclasses.replace(config.depth, normalisation="calibrated", calibration_path=str(path))
    normaliser = DistanceNormaliser(cfg)
    assert normaliser.distance(disparity_map(), Box(0.6, 0.6, 0.9, 0.9)) == pytest.approx(5 / 8)


def test_missing_calibration_is_explained(config: Config, tmp_path: Path) -> None:
    cfg = dataclasses.replace(
        config.depth, normalisation="calibrated", calibration_path=str(tmp_path / "none.yaml")
    )
    with pytest.raises(ConfigError, match="naadrik calibrate"):
        DistanceNormaliser(cfg)


def test_inverted_calibration_rejected() -> None:
    with pytest.raises(ConfigError):
        Calibration(near_disparity=1.0, far_disparity=5.0)


@pytest.mark.parametrize(
    ("distance", "level"), [(0.0, 0), (0.32, 0), (0.34, 1), (0.66, 1), (0.7, 2), (1.0, 2)]
)
def test_quantise_distance_without_history(distance: float, level: int) -> None:
    assert quantise_distance(distance, None, 3, 0.08) == level


def test_quantise_distance_hysteresis() -> None:
    assert quantise_distance(0.36, 0, 3, 0.08) == 0  # just over the edge: hold
    assert quantise_distance(0.45, 0, 3, 0.08) == 1  # clearly over: move
    assert quantise_distance(0.30, 1, 3, 0.08) == 1


def test_level_to_distance() -> None:
    assert [level_to_distance(i, 3) for i in range(3)] == [0.0, 0.5, 1.0]


# --- Tracker ---------------------------------------------------------------------------


def det(x: float, label: str = "person", size: float = 0.2) -> Detection:
    return Detection(Box(x, 0.4, x + size, 0.4 + size), label, 0.9)


def test_tracker_keeps_identity_and_smooths(config: Config) -> None:
    tracker = Tracker(config.tracking)
    first = tracker.update([det(0.10)], 0.0)[0]
    second = tracker.update([det(0.15)], 0.1)[0]
    assert second.id == first.id
    expected_x0 = 0.10 + config.tracking.position_smoothing * 0.05
    assert second.box.x0 == pytest.approx(expected_x0)
    assert second.velocity[0] > 0


def test_tracker_does_not_match_across_labels(config: Config) -> None:
    tracker = Tracker(config.tracking)
    a = tracker.update([det(0.1, "person")], 0.0)[0]
    b = tracker.update([det(0.1, "dog")], 0.1)[0]
    assert a.id != b.id


def test_tracker_confirms_and_expires(config: Config) -> None:
    tracker = Tracker(config.tracking)
    tracker.update([det(0.1)], 0.0)
    assert tracker.confirmed() == []
    tracker.update([det(0.1)], 0.1)
    assert len(tracker.confirmed()) == 1
    for i in range(config.tracking.max_missed_frames):
        tracker.update([], 0.2 + i * 0.1)
    assert len(tracker.tracks) == 1 and tracker.confirmed() == []
    tracker.update([], 5.0)
    assert tracker.tracks == []


def test_distance_rate_detects_approach(config: Config) -> None:
    tracker = Tracker(config.tracking)
    track = tracker.update([det(0.4)], 0.0)[0]
    for i in range(20):
        tracker.update_distance(track, 1.0 - i * 0.05, i * 0.1)
    assert track.distance_rate < -0.2


# --- Prioritiser -----------------------------------------------------------------------


def track(tid: int, label: str, x: float, distance: float, rate: float = 0.0) -> Track:
    box = Box(x - 0.05, 0.4, x + 0.05, 0.5)
    return Track(tid, label, 0.9, box, 0.0, distance=distance, distance_rate=rate)


def test_score_formula(config: Config) -> None:
    cfg = config.priority
    centred_person = track(1, "person", 0.5, 0.2)
    assert priority_score(centred_person, cfg) == pytest.approx(0.8 * 1.0 * 1.0)
    edge_cup = track(2, "cup", 0.0, 0.2)
    assert priority_score(edge_cup, cfg) == pytest.approx(0.8 * 0.4 * (1 - cfg.centre_weight))
    unknown = track(3, "kite", 0.5, 0.0)
    assert priority_score(unknown, cfg) == pytest.approx(cfg.default_importance)


def test_approaching_object_is_boosted(config: Config) -> None:
    cfg = config.priority
    still = priority_score(track(1, "car", 0.5, 0.5), cfg)
    approaching = priority_score(track(2, "car", 0.5, 0.5, rate=-1.0), cfg)
    assert approaching == pytest.approx(still * (1 + cfg.motion_boost))


def test_selection_caps_and_orders(config: Config) -> None:
    prioritiser = Prioritiser(config.priority, 3)
    tracks = [track(i, "person", 0.5, d) for i, d in enumerate([0.9, 0.1, 0.5, 0.3, 0.7])]
    chosen = prioritiser.select(tracks)
    assert [t.id for t, _ in chosen] == [1, 3, 2]


def test_selection_is_sticky_within_margin(config: Config) -> None:
    prioritiser = Prioritiser(config.priority, 1)
    a, b = track(1, "person", 0.5, 0.30), track(2, "person", 0.5, 0.35)
    assert prioritiser.select([a, b])[0][0].id == 1
    b.distance = 0.25  # slightly better than a, but within the switch margin
    assert prioritiser.select([a, b])[0][0].id == 1
    b.distance = 0.0  # clearly better
    assert prioritiser.select([a, b])[0][0].id == 2
