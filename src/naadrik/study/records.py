"""Trial records and their CSV form."""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from naadrik.stimuli import AXES


@dataclass(frozen=True)
class TrialRecord:
    participant: str
    condition: str
    phase: str
    trial: int
    side: str
    height: str
    distance: str
    colour: str
    resp_side: str
    resp_height: str
    resp_distance: str
    resp_colour: str
    correct_side: bool
    correct_height: bool
    correct_distance: bool
    correct_colour: bool
    all_correct: bool
    rt_first_s: float
    rt_total_s: float
    replays: int
    timestamp: str

    def correct(self, axis: str) -> bool:
        return bool(getattr(self, f"correct_{axis}"))


FIELDNAMES = [field.name for field in fields(TrialRecord)]


class TrialWriter:
    """Appends one row per trial and flushes, so a crash never loses completed trials."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._handle = path.open("w", newline="", encoding="utf-8")
        self._writer = csv.DictWriter(self._handle, fieldnames=FIELDNAMES)
        self._writer.writeheader()
        self._handle.flush()

    def write(self, record: TrialRecord) -> None:
        self._writer.writerow(asdict(record))
        self._handle.flush()

    def close(self) -> None:
        self._handle.close()


def read_trials(path: Path) -> list[TrialRecord]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    records = []
    for row in rows:
        values: dict[str, object] = dict(row)
        for axis in AXES:
            values[f"correct_{axis}"] = row[f"correct_{axis}"] == "True"
        values["all_correct"] = row["all_correct"] == "True"
        values["trial"] = int(row["trial"])
        values["replays"] = int(row["replays"])
        values["rt_first_s"] = float(row["rt_first_s"])
        values["rt_total_s"] = float(row["rt_total_s"])
        records.append(TrialRecord(**values))  # type: ignore[arg-type]
    return records
