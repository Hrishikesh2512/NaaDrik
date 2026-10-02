"""Training sessions are counted on disk so spoken labels can fade out as the user learns."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import yaml

from naadrik.config import TrainingConfig
from naadrik.errors import ConfigError


def default_progress_path() -> Path:
    data_home = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(data_home) / "naadrik" / "training.yaml"


def speech_probability(session: int, cfg: TrainingConfig) -> float:
    """Chance of announcing an object in a given (1-based) session.

    Full speech for the first ``full_speech_sessions``, then a linear fade to zero over
    ``fade_sessions`` so the user leans on the sounds alone.
    """
    if session <= cfg.full_speech_sessions:
        return 1.0
    if cfg.fade_sessions == 0:
        return 0.0
    into_fade = session - cfg.full_speech_sessions
    return max(0.0, 1.0 - into_fade / (cfg.fade_sessions + 1))


@dataclass
class TrainingProgress:
    path: Path
    sessions: int = 0
    last_session: str | None = None

    @classmethod
    def load(cls, cfg: TrainingConfig) -> TrainingProgress:
        path = Path(cfg.progress_path) if cfg.progress_path else default_progress_path()
        if not path.is_file():
            return cls(path)
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            return cls(path, int(data.get("sessions", 0)), data.get("last_session"))
        except (yaml.YAMLError, TypeError, ValueError) as exc:
            raise ConfigError(
                f"Training progress file {path} is malformed ({exc}). Delete it or run "
                "`naadrik train --reset-progress`."
            ) from exc

    def start_session(self) -> int:
        self.sessions += 1
        self.last_session = datetime.now(UTC).isoformat(timespec="seconds")
        self.save()
        return self.sessions

    def reset(self) -> None:
        self.sessions = 0
        self.last_session = None
        self.save()

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"sessions": self.sessions, "last_session": self.last_session}
        self.path.write_text(yaml.safe_dump(payload), encoding="utf-8")
