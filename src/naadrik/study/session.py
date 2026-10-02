"""Runs one participant through baseline, training and test for one sonification condition."""

from __future__ import annotations

import json
import random
import re
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from naadrik import __version__
from naadrik.config import Config
from naadrik.errors import ConfigError
from naadrik.sound_engine import SoundEngine
from naadrik.stimuli import AXES, COLOURS, Stimulus, sample
from naadrik.study.baseline_sonifier import BaselineSonifier
from naadrik.study.instructions import intro
from naadrik.study.records import TrialRecord, TrialWriter
from naadrik.study.responders import REPLAY, Responder, SimulatedResponder, axis_options

CONDITIONS = ("naadrik", "voice")
PHASES = ("baseline", "training", "test")
Player = Callable[[np.ndarray], None]


def validate_participant(participant: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", participant):
        raise ConfigError(
            "Participant id must be 1-40 letters, digits, '-' or '_' (it becomes a file name)."
        )
    return participant


class StimulusRenderer:
    """Renders stimuli for one condition, caching because trials repeat grid cells."""

    def __init__(self, config: Config, condition: str, engine: SoundEngine | None = None) -> None:
        self._config = config
        self._condition = condition
        self._duration = config.study.stimulus_s
        self.sample_rate = config.audio.sample_rate
        if condition == "naadrik":
            self._engine = engine or SoundEngine(config)
        else:
            self._baseline = BaselineSonifier(config.study.baseline_sonifier, self.sample_rate)
        self._cache: dict[Stimulus, np.ndarray] = {}

    def render(self, stimulus: Stimulus) -> np.ndarray:
        audio = self._cache.get(stimulus)
        if audio is None:
            if self._condition == "naadrik":
                state = stimulus.state()
                audio = self._engine.render_object(
                    state.x, state.y, state.distance, state.r, state.g, state.b, self._duration
                )
            else:
                audio = self._baseline.render_stimulus(stimulus, self._duration)
            self._cache[stimulus] = audio
        return audio


class StudySession:
    def __init__(
        self,
        config: Config,
        participant: str,
        condition: str,
        responder: Responder,
        play: Player,
        rng: random.Random | None = None,
        renderer: StimulusRenderer | None = None,
    ) -> None:
        if condition not in CONDITIONS:
            raise ConfigError(f"Unknown condition {condition!r}; choose from {CONDITIONS}.")
        unknown = set(config.study.colours) - set(COLOURS)
        if unknown:
            raise ConfigError(
                f"study.colours has unknown colour(s) {sorted(unknown)}; known: {list(COLOURS)}"
            )
        self._config = config
        self._participant = validate_participant(participant)
        self._condition = condition
        self._responder = responder
        self._play = play
        self._rng = rng or random.Random()
        self._renderer = renderer or StimulusRenderer(config, condition)
        self._colours = tuple(config.study.colours)

    def run(self, phases: tuple[str, ...] = PHASES) -> Path:
        stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        base = (
            Path(self._config.study.results_dir) / f"{self._participant}_{self._condition}_{stamp}"
        )
        writer = TrialWriter(base.with_suffix(".csv"))
        session: dict[str, object] = {
            "participant": self._participant,
            "condition": self._condition,
            "naadrik_version": __version__,
            "started": datetime.now(UTC).isoformat(timespec="seconds"),
            "colours": list(self._colours),
            "stimulus_s": self._config.study.stimulus_s,
            "phases": {},
        }
        try:
            for phase in phases:
                started = time.monotonic()
                count = self._run_phase(phase, writer)
                session["phases"][phase] = {  # type: ignore[index]
                    "trials": count,
                    "duration_s": round(time.monotonic() - started, 3),
                }
        finally:
            writer.close()
            session["finished"] = datetime.now(UTC).isoformat(timespec="seconds")
            base.with_suffix(".json").write_text(json.dumps(session, indent=2), encoding="utf-8")
        return writer.path

    def _phase_trials(self, phase: str) -> int:
        return int(getattr(self._config.study, f"{phase}_trials"))

    def _run_phase(self, phase: str, writer: TrialWriter) -> int:
        count = self._phase_trials(phase)
        if count == 0:
            return 0
        self._responder.show(f"\n=== {phase.upper()} ===\n{intro(phase, self._condition)}")
        self._responder.wait_to_start("")
        for index, stimulus in enumerate(sample(count, self._rng, self._colours), start=1):
            self._responder.show(f"\nTrial {index}/{count}")
            record = self._trial(phase, index, stimulus)
            writer.write(record)
            if phase == "training":
                self._feedback(record, stimulus)
        return count

    def _trial(self, phase: str, index: int, stimulus: Stimulus) -> TrialRecord:
        if isinstance(self._responder, SimulatedResponder):
            self._responder.stimulus = stimulus
        audio = self._renderer.render(stimulus)
        self._play(audio)
        # Reaction times run from the end of the stimulus: playback blocks until then.
        offset = time.perf_counter()
        answers: dict[str, str] = {}
        first: float | None = None
        replays = 0
        for axis in AXES:
            while True:
                answer = self._responder.choose(axis, axis_options(axis, self._colours))
                if answer != REPLAY:
                    break
                replays += 1
                self._play(audio)
            if first is None:
                first = time.perf_counter() - offset
            answers[axis] = answer
        total = time.perf_counter() - offset
        correct = {axis: answers[axis] == stimulus.value(axis) for axis in AXES}
        return TrialRecord(
            participant=self._participant,
            condition=self._condition,
            phase=phase,
            trial=index,
            side=stimulus.side,
            height=stimulus.height,
            distance=stimulus.distance,
            colour=stimulus.colour,
            resp_side=answers["side"],
            resp_height=answers["height"],
            resp_distance=answers["distance"],
            resp_colour=answers["colour"],
            correct_side=correct["side"],
            correct_height=correct["height"],
            correct_distance=correct["distance"],
            correct_colour=correct["colour"],
            all_correct=all(correct.values()),
            rt_first_s=round(first or 0.0, 4),
            rt_total_s=round(total, 4),
            replays=replays,
            timestamp=datetime.now(UTC).isoformat(timespec="milliseconds"),
        )

    def _feedback(self, record: TrialRecord, stimulus: Stimulus) -> None:
        marks = ", ".join(f"{axis} {'right' if record.correct(axis) else 'wrong'}" for axis in AXES)
        answer = f"{stimulus.side}, {stimulus.height}, {stimulus.distance}, {stimulus.colour}"
        self._responder.show(f"  Answer: {answer}. ({marks}) Listen again.")
        self._play(self._renderer.render(stimulus))
