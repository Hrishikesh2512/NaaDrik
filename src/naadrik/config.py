"""Typed configuration loaded from ``config.yaml``.

The YAML is mapped onto frozen dataclasses. Unknown or missing keys are errors so that a
typo in the file fails loudly instead of silently falling back to a default.
"""

from __future__ import annotations

import dataclasses
import os
import types
import typing
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from naadrik.errors import ConfigError

CONFIG_ENV_VAR = "NAADRIK_CONFIG"
CONFIG_FILENAME = "config.yaml"


@dataclass(frozen=True)
class AudioConfig:
    sample_rate: int
    block_size: int
    master_gain: float
    device: str | int | None

    def __post_init__(self) -> None:
        _require(self.sample_rate >= 8000, "audio.sample_rate must be at least 8000")
        _require(self.block_size > 0, "audio.block_size must be positive")
        _require(0.0 < self.master_gain <= 2.0, "audio.master_gain must be in (0, 2]")


@dataclass(frozen=True)
class PitchConfig:
    base_hz: float
    octaves: float
    scale: tuple[int, ...]

    def __post_init__(self) -> None:
        _require(self.base_hz > 20.0, "pitch.base_hz must be above 20 Hz")
        _require(self.octaves > 0.0, "pitch.octaves must be positive")
        _require(len(self.scale) > 0, "pitch.scale must not be empty")
        _require(
            all(0 <= step < 12 for step in self.scale) and self.scale[0] == 0,
            "pitch.scale must start at 0 and hold semitone offsets below 12",
        )


@dataclass(frozen=True)
class PulseConfig:
    near_hz: float
    far_hz: float
    duty_cycle: float
    max_gate_s: float
    attack_ms: float
    release_ms: float

    def __post_init__(self) -> None:
        _require(self.near_hz > self.far_hz > 0.0, "pulse.near_hz must exceed pulse.far_hz > 0")
        _require(0.0 < self.duty_cycle < 1.0, "pulse.duty_cycle must be in (0, 1)")
        _require(self.max_gate_s > 0.0, "pulse.max_gate_s must be positive")
        _require(self.attack_ms >= 0.0 and self.release_ms > 0.0, "pulse envelope times invalid")


@dataclass(frozen=True)
class ColourConfig:
    thresholds: tuple[float, float]
    levels: tuple[float, float, float]

    def __post_init__(self) -> None:
        low, high = self.thresholds
        _require(0.0 < low < high < 1.0, "colour.thresholds must satisfy 0 < low < high < 1")
        _require(self.levels[0] == 0.0, "colour.levels[0] must be 0 so 'off' is silent")
        _require(self.levels[0] < self.levels[1] < self.levels[2], "colour.levels must increase")


@dataclass(frozen=True)
class PluckConfig:
    gain: float
    decay_s: float
    brightness: float
    buzz: float
    sympathetic: float


@dataclass(frozen=True)
class BowedConfig:
    gain: float
    vibrato_hz: float
    vibrato_cents: float
    vibrato_delay_s: float
    cutoff_hz: float
    body_resonances_hz: tuple[float, ...]
    bow_noise: float


@dataclass(frozen=True)
class FluteConfig:
    gain: float
    harmonics: tuple[float, ...]
    breath: float
    chiff: float
    vibrato_hz: float
    vibrato_cents: float
    tremolo_depth: float


@dataclass(frozen=True)
class InstrumentsConfig:
    note_duration_s: float
    pluck: PluckConfig
    bowed: BowedConfig
    flute: FluteConfig


@dataclass(frozen=True)
class SpatialConfig:
    mode: str
    max_azimuth_deg: float
    head_radius_m: float
    extra_ild_db: float
    rear_lowpass_hz: float
    smoothing_ms: float

    def __post_init__(self) -> None:
        _require(self.mode in ("head_model", "pan"), "spatial.mode must be head_model or pan")
        _require(0.0 < self.max_azimuth_deg <= 90.0, "spatial.max_azimuth_deg must be in (0, 90]")
        _require(self.smoothing_ms >= 0.0, "spatial.smoothing_ms must not be negative")


@dataclass(frozen=True)
class ObjectsConfig:
    max_objects: int

    def __post_init__(self) -> None:
        _require(1 <= self.max_objects <= 8, "objects.max_objects must be between 1 and 8")


@dataclass(frozen=True)
class Config:
    audio: AudioConfig
    pitch: PitchConfig
    pulse: PulseConfig
    colour: ColourConfig
    instruments: InstrumentsConfig
    spatial: SpatialConfig
    objects: ObjectsConfig

    def __post_init__(self) -> None:
        longest_event = self.pulse.max_gate_s + self.pulse.release_ms / 1000.0
        _require(
            self.instruments.note_duration_s >= longest_event,
            "instruments.note_duration_s must be at least pulse.max_gate_s + pulse.release_ms",
        )


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ConfigError(message)


def default_config_path() -> Path:
    """Resolve the config file: $NAADRIK_CONFIG, then ./config.yaml, then the repository copy."""
    env_path = os.environ.get(CONFIG_ENV_VAR)
    if env_path:
        return Path(env_path)
    cwd_path = Path.cwd() / CONFIG_FILENAME
    if cwd_path.is_file():
        return cwd_path
    return Path(__file__).resolve().parents[2] / CONFIG_FILENAME


def load_config(path: str | Path | None = None) -> Config:
    config_path = Path(path) if path is not None else default_config_path()
    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(
            f"Config file not found: {config_path}. Pass --config or set {CONFIG_ENV_VAR}."
        ) from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"Config file {config_path} is not valid YAML: {exc}") from exc
    return config_from_dict(raw)


def config_from_dict(data: Any) -> Config:
    return _build(Config, data, "config")


def _build(cls: type, data: Any, where: str) -> Any:
    if not isinstance(data, dict):
        raise ConfigError(f"{where} must be a mapping, got {type(data).__name__}")
    hints = typing.get_type_hints(cls)
    names = {field.name for field in dataclasses.fields(cls)}
    unknown = set(data) - names
    missing = names - set(data)
    if unknown:
        raise ConfigError(f"{where}: unknown key(s) {sorted(unknown)}")
    if missing:
        raise ConfigError(f"{where}: missing key(s) {sorted(missing)}")
    values = {name: _coerce(hints[name], data[name], f"{where}.{name}") for name in names}
    return cls(**values)


def _coerce(hint: Any, value: Any, where: str) -> Any:
    if dataclasses.is_dataclass(hint):
        return _build(hint, value, where)
    origin = typing.get_origin(hint)
    if origin is tuple:
        if not isinstance(value, list | tuple):
            raise ConfigError(f"{where} must be a list")
        args = typing.get_args(hint)
        if len(args) == 2 and args[1] is Ellipsis:
            return tuple(_coerce(args[0], item, where) for item in value)
        if len(value) != len(args):
            raise ConfigError(f"{where} must have exactly {len(args)} items")
        return tuple(_coerce(arg, item, where) for arg, item in zip(args, value, strict=True))
    if origin in (typing.Union, types.UnionType):
        for option in typing.get_args(hint):
            if option is type(None) and value is None:
                return None
            if option is not type(None) and isinstance(value, option):
                return value
        raise ConfigError(f"{where} has unsupported value {value!r}")
    if hint is float and isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    if hint is int and isinstance(value, int) and not isinstance(value, bool):
        return value
    if hint is str and isinstance(value, str):
        return value
    raise ConfigError(f"{where} must be {getattr(hint, '__name__', hint)}, got {value!r}")
