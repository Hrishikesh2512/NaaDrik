import dataclasses
import json
import random
from pathlib import Path

import numpy as np
import pytest

from naadrik.config import Config
from naadrik.errors import ConfigError
from naadrik.stimuli import Stimulus
from naadrik.study.analysis import (
    OVERALL,
    StudyResults,
    analyse,
    chance_levels,
    format_report,
    holm_adjust,
    wilson_interval,
)
from naadrik.study.baseline_sonifier import BaselineSonifier, row_frequencies, stimulus_image
from naadrik.study.records import read_trials
from naadrik.study.responders import REPLAY, SimulatedResponder, option_keys
from naadrik.study.session import StudySession, validate_participant

SR = 48000

# --- Baseline sonifier -----------------------------------------------------------------


def test_row_frequencies_rise_to_the_top(config: Config) -> None:
    freqs = row_frequencies(config.study.baseline_sonifier)
    cfg = config.study.baseline_sonifier
    assert freqs[0] == pytest.approx(cfg.high_hz)
    assert freqs[-1] == pytest.approx(cfg.low_hz)
    assert np.all(np.diff(freqs) < 0)


def test_image_disc_position_size_and_grey(config: Config) -> None:
    cfg = config.study.baseline_sonifier
    near = stimulus_image(Stimulus("left", "high", "near", "white"), cfg)
    far = stimulus_image(Stimulus("left", "high", "far", "white"), cfg)
    assert near.sum() > 4 * far.sum()
    rows, cols = np.nonzero(near)
    assert cols.mean() < cfg.columns / 3 and rows.mean() < cfg.rows / 3
    blue = stimulus_image(Stimulus("centre", "middle", "mid", "blue"), cfg)
    assert blue.max() == pytest.approx(0.114)


def sweep_energy(audio: np.ndarray, sweep_s: float) -> tuple[np.ndarray, np.ndarray]:
    """Energy per tenth of the first sweep, for left and right channels."""
    first = audio[: int(sweep_s * SR)]
    tenths = np.array_split(first**2, 10)
    return np.array([t[:, 0].sum() for t in tenths]), np.array([t[:, 1].sum() for t in tenths])


def test_left_object_sounds_early_and_left(config: Config) -> None:
    cfg = dataclasses.replace(config.study.baseline_sonifier, click=False)
    sonifier = BaselineSonifier(cfg, SR)
    audio = sonifier.render_stimulus(Stimulus("left", "middle", "near", "white"), 1.0)
    left, right = sweep_energy(audio, cfg.sweep_s)
    total = left + right
    assert total[:4].sum() > 10 * total[6:].sum()
    assert left.sum() > right.sum()


def test_higher_object_has_higher_pitch(config: Config) -> None:
    cfg = dataclasses.replace(config.study.baseline_sonifier, click=False)
    sonifier = BaselineSonifier(cfg, SR)

    def centroid(height: str) -> float:
        audio = sonifier.render_stimulus(Stimulus("centre", height, "mid", "white"), 1.0)
        power = np.abs(np.fft.rfft(audio.sum(axis=1))) ** 2
        return float((np.fft.rfftfreq(len(audio), 1 / SR) * power).sum() / power.sum())

    assert centroid("high") > 2 * centroid("low")


def test_sweeps_repeat(config: Config) -> None:
    sonifier = BaselineSonifier(config.study.baseline_sonifier, SR)
    audio = sonifier.render_stimulus(Stimulus("left", "middle", "near", "red"), 3.0)
    assert audio.shape == (3 * SR, 2)
    assert np.max(np.abs(audio)) <= 1.0
    sweep_s = config.study.baseline_sonifier.sweep_s
    first = np.add(*sweep_energy(audio, sweep_s))
    second = np.add(*sweep_energy(audio[int(sweep_s * SR) :], sweep_s))
    np.testing.assert_allclose(first, second, rtol=0.1, atol=1e-3 * first.max())


# --- Session ---------------------------------------------------------------------------


def study_config(config: Config, tmp_path: Path, **counts: int) -> Config:
    study = dataclasses.replace(
        config.study,
        results_dir=str(tmp_path),
        stimulus_s=0.2,
        baseline_trials=counts.get("baseline", 3),
        training_trials=counts.get("training", 4),
        test_trials=counts.get("test", 5),
    )
    return dataclasses.replace(config, study=study)


@pytest.mark.parametrize("condition", ["naadrik", "voice"])
def test_oracle_session_writes_correct_results(
    config: Config, tmp_path: Path, condition: str
) -> None:
    cfg = study_config(config, tmp_path)
    played: list[int] = []
    rng = random.Random(0)
    session = StudySession(
        cfg,
        "sim-P1",
        condition,
        SimulatedResponder("oracle", rng),
        lambda a: played.append(len(a)),
        rng,
    )
    csv_path = session.run()
    records = read_trials(csv_path)
    assert [r.phase for r in records] == ["baseline"] * 3 + ["training"] * 4 + ["test"] * 5
    assert all(r.all_correct for r in records)
    assert len(played) == 3 + 2 * 4 + 5  # training replays the stimulus after feedback
    meta = json.loads(csv_path.with_suffix(".json").read_text())
    assert meta["condition"] == condition
    assert set(meta["phases"]) == {"baseline", "training", "test"}
    assert meta["phases"]["training"]["trials"] == 4


class ReplayOnceResponder(SimulatedResponder):
    def __init__(self) -> None:
        super().__init__("oracle", random.Random(0))
        self.replayed = False

    def choose(self, axis: str, options: tuple[str, ...]) -> str:
        if not self.replayed:
            self.replayed = True
            return REPLAY
        return super().choose(axis, options)


def test_replay_is_counted(config: Config, tmp_path: Path) -> None:
    cfg = study_config(config, tmp_path, baseline=0, training=0, test=1)
    played: list[int] = []
    session = StudySession(cfg, "P2", "naadrik", ReplayOnceResponder(), lambda a: played.append(1))
    record = read_trials(session.run())[0]
    assert record.replays == 1 and len(played) == 2


def test_invalid_inputs_rejected(config: Config, tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        validate_participant("../etc")
    with pytest.raises(ConfigError):
        StudySession(config, "P1", "sonar", SimulatedResponder("random", random.Random()), print)
    study = dataclasses.replace(config.study, colours=("red", "chartreuse"))
    with pytest.raises(ConfigError, match="chartreuse"):
        StudySession(
            dataclasses.replace(config, study=study),
            "P1",
            "naadrik",
            SimulatedResponder("random", random.Random()),
            print,
        )


def test_option_keys() -> None:
    assert option_keys(("left", "centre", "right")) == {"l": "left", "c": "centre", "r": "right"}
    assert option_keys(("green", "grey")) == {"1": "green", "2": "grey"}


# --- Analysis --------------------------------------------------------------------------


def test_wilson_interval() -> None:
    low, high = wilson_interval(8, 10)
    assert low == pytest.approx(0.490, abs=1e-3) and high == pytest.approx(0.943, abs=1e-3)
    assert wilson_interval(0, 10)[0] == 0.0


def test_holm_adjust() -> None:
    np.testing.assert_allclose(holm_adjust([0.01, 0.04, 0.03]), [0.03, 0.06, 0.06])


def test_chance_levels() -> None:
    levels = chance_levels(5)
    assert levels["side"] == pytest.approx(1 / 3)
    assert levels["colour"] == pytest.approx(0.2)
    assert levels[OVERALL] == pytest.approx(0.2 / 27)


def test_random_participant_is_near_chance_and_oracle_is_perfect(
    config: Config, tmp_path: Path
) -> None:
    cfg = study_config(config, tmp_path, baseline=0, training=0, test=300)
    rng = random.Random(3)
    for kind in ("random", "oracle"):
        StudySession(
            cfg, f"sim-{kind}", "voice", SimulatedResponder(kind, rng), lambda a: None, rng
        ).run(("test",))
    results = StudyResults.load([tmp_path])
    by_participant = {}
    for participant in ("sim-random", "sim-oracle"):
        subset = StudyResults(
            [r for r in results.records if r.participant == participant], results.sessions
        )
        by_participant[participant] = subset.summaries()[0].axes
    random_axes = by_participant["sim-random"]
    assert random_axes["side"].accuracy == pytest.approx(1 / 3, abs=0.07)
    assert random_axes["colour"].accuracy == pytest.approx(0.2, abs=0.06)
    assert by_participant["sim-oracle"][OVERALL].accuracy == 1.0
    assert by_participant["sim-oracle"][OVERALL].p_value < 1e-6

    report, charts = analyse([tmp_path], tmp_path / "report")
    text = report.read_text()
    assert "simulated participants" in text and "p (Holm)" in text
    assert all(chart.is_file() and chart.stat().st_size > 10_000 for chart in charts)
    assert "| vOICe-style baseline | test | side |" in format_report(results)
