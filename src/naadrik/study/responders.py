"""Ways of collecting a participant's answers: the keyboard, or simulated participants."""

from __future__ import annotations

import random
import sys
import time
from typing import Protocol

from naadrik.errors import NaadrikError
from naadrik.stimuli import OPTIONS, Stimulus

REPLAY = "replay"


class Responder(Protocol):
    def choose(self, axis: str, options: tuple[str, ...]) -> str:
        """Return one of ``options``, or REPLAY to hear the stimulus again."""

    def show(self, text: str) -> None: ...

    def wait_to_start(self, prompt: str) -> None: ...


def option_keys(options: tuple[str, ...]) -> dict[str, str]:
    """Single keys for each option: first letters where unique, else digits."""
    initials = [option[0] for option in options]
    if len(set(initials)) == len(options):
        return dict(zip(initials, options, strict=True))
    return {str(i + 1): option for i, option in enumerate(options)}


def _read_key() -> str:
    """One keypress without Enter on a terminal; a line on anything else."""
    if not sys.stdin.isatty():
        line = sys.stdin.readline()
        if not line:
            raise NaadrikError("Input ended before the study finished; completed trials are saved.")
        return line.strip()[:1]
    import termios
    import tty

    fd = sys.stdin.fileno()
    previous = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        return sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, previous)


class KeyboardResponder:
    def choose(self, axis: str, options: tuple[str, ...]) -> str:
        keys = option_keys(options)
        listing = "  ".join(f"[{key}] {option}" for key, option in keys.items())
        print(f"  {axis.capitalize()}?  {listing}  [space] replay", flush=True)
        while True:
            key = _read_key().lower()
            if key == " ":
                return REPLAY
            if key in keys:
                print(f"    -> {keys[key]}", flush=True)
                return keys[key]
            if key == "\x03":
                raise KeyboardInterrupt

    def show(self, text: str) -> None:
        print(text, flush=True)

    def wait_to_start(self, prompt: str) -> None:
        print(f"{prompt} Press any key to start.".strip(), flush=True)
        if _read_key() == "\x03":
            raise KeyboardInterrupt


class SimulatedResponder:
    """Answers without a person, to validate the protocol and the analysis.

    ``oracle`` always answers correctly; ``random`` guesses uniformly and should land at
    chance. Results are labelled with a ``sim-`` participant id.
    """

    def __init__(self, kind: str, rng: random.Random) -> None:
        if kind not in ("oracle", "random"):
            raise ValueError(f"unknown simulated participant {kind!r}")
        self.kind = kind
        self._rng = rng
        self.stimulus: Stimulus | None = None

    def choose(self, axis: str, options: tuple[str, ...]) -> str:
        if self.kind == "oracle" and self.stimulus is not None:
            return self.stimulus.value(axis)
        return self._rng.choice(options)

    def show(self, text: str) -> None:
        pass

    def wait_to_start(self, prompt: str) -> None:
        pass


def axis_options(axis: str, colours: tuple[str, ...]) -> tuple[str, ...]:
    return colours if axis == "colour" else OPTIONS[axis]


def now() -> float:
    return time.perf_counter()
