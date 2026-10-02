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
    live_latency_s: float

    def __post_init__(self) -> None:
        _require(self.sample_rate >= 8000, "audio.sample_rate must be at least 8000")
        _require(0.0 < self.live_latency_s <= 0.5, "audio.live_latency_s must be in (0, 0.5]")
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
    central_fraction: float
    white_balance: bool

    def __post_init__(self) -> None:
        _require(0.0 < self.central_fraction <= 1.0, "colour.central_fraction must be in (0, 1]")
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
    drive: float
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
class PresenceConfig:
    level: float
    cutoff_ratio: float
    noise: float

    def __post_init__(self) -> None:
        _require(
            0.0 < self.level <= 1.0,
            "instruments.presence.level must be in (0, 1]: every object must stay audible, "
            "including black ones",
        )
        _require(self.cutoff_ratio >= 1.0, "instruments.presence.cutoff_ratio must be >= 1")
        _require(0.0 <= self.noise < 1.0, "instruments.presence.noise must be in [0, 1)")


@dataclass(frozen=True)
class InstrumentsConfig:
    note_duration_s: float
    pluck: PluckConfig
    bowed: BowedConfig
    presence: PresenceConfig
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
class CameraConfig:
    index: int
    capture_width: int
    capture_height: int
    fps: int
    process_width: int

    def __post_init__(self) -> None:
        _require(self.index >= 0, "camera.index must not be negative")
        _require(64 <= self.process_width <= self.capture_width, "camera.process_width invalid")


@dataclass(frozen=True)
class DetectionConfig:
    model_path: str
    score_threshold: float
    max_results: int

    def __post_init__(self) -> None:
        _require(0.0 < self.score_threshold < 1.0, "detection.score_threshold must be in (0, 1)")


@dataclass(frozen=True)
class DepthConfig:
    model_path: str
    every_n_frames: int
    input_width: int
    threads: int
    box_fraction: float
    normalisation: str
    calibration_path: str
    levels: int
    hysteresis: float

    def __post_init__(self) -> None:
        _require(self.every_n_frames >= 1, "depth.every_n_frames must be at least 1")
        _require(self.input_width % 14 == 0, "depth.input_width must be a multiple of 14")
        _require(
            self.normalisation in ("scene", "calibrated"),
            "depth.normalisation must be scene or calibrated",
        )
        _require(self.levels == 0 or self.levels >= 2, "depth.levels must be 0 or at least 2")
        _require(0.0 <= self.hysteresis < 0.5, "depth.hysteresis must be in [0, 0.5)")


@dataclass(frozen=True)
class TrackingConfig:
    iou_threshold: float
    max_missed_frames: int
    min_hits: int
    position_smoothing: float
    distance_smoothing: float
    colour_smoothing: float

    def __post_init__(self) -> None:
        for name in ("position_smoothing", "distance_smoothing", "colour_smoothing"):
            _require(0.0 < getattr(self, name) <= 1.0, f"tracking.{name} must be in (0, 1]")


@dataclass(frozen=True)
class PriorityConfig:
    class_importance: dict[str, float]
    default_importance: float
    centre_weight: float
    motion_boost: float
    approach_speed: float
    moving_speed: float
    switch_margin: float

    def __post_init__(self) -> None:
        _require(0.0 <= self.centre_weight <= 1.0, "priority.centre_weight must be in [0, 1]")


@dataclass(frozen=True)
class TrainingConfig:
    tts_command: str
    voice: str
    words_per_minute: int
    speech_gain: float
    spatialise_speech: bool
    duck_db: float
    gap_s: float
    repeat_s: float
    include_height: bool
    full_speech_sessions: int
    fade_sessions: int
    progress_path: str | None

    def __post_init__(self) -> None:
        _require(80 <= self.words_per_minute <= 450, "training.words_per_minute must be 80-450")
        _require(self.duck_db >= 0.0, "training.duck_db must not be negative")
        _require(self.full_speech_sessions >= 0, "training.full_speech_sessions must be >= 0")
        _require(self.fade_sessions >= 0, "training.fade_sessions must be >= 0")


@dataclass(frozen=True)
class BaselineSonifierConfig:
    sweep_s: float
    rows: int
    columns: int
    low_hz: float
    high_hz: float
    greyscale: str
    click: bool

    def __post_init__(self) -> None:
        _require(self.sweep_s > 0.0, "study.baseline_sonifier.sweep_s must be positive")
        _require(self.rows >= 2 and self.columns >= 2, "baseline sonifier needs >= 2 rows/columns")
        _require(0.0 < self.low_hz < self.high_hz, "baseline sonifier: low_hz < high_hz required")
        _require(self.greyscale in ("luma", "mean"), "greyscale must be luma or mean")


@dataclass(frozen=True)
class StudyConfig:
    stimulus_s: float
    colours: tuple[str, ...]
    baseline_trials: int
    training_trials: int
    test_trials: int
    results_dir: str
    baseline_sonifier: BaselineSonifierConfig

    def __post_init__(self) -> None:
        _require(self.stimulus_s > 0.0, "study.stimulus_s must be positive")
        _require(len(self.colours) >= 2, "study.colours needs at least two colours")
        _require(len(set(self.colours)) == len(self.colours), "study.colours has duplicates")
        for name in ("baseline_trials", "training_trials", "test_trials"):
            _require(getattr(self, name) >= 0, f"study.{name} must not be negative")


@dataclass(frozen=True)
class AndroidConfig:
    """Read by the Android app only; validated here so both loaders accept the same file."""

    detection_model: str
    depth_model: str
    depth_input_size: int
    depth_delegate: str
    depth_threads: int
    detection_delegate: str
    analysis_width: int
    analysis_height: int
    use_arcore_depth: bool

    def __post_init__(self) -> None:
        for name in ("depth_delegate", "detection_delegate"):
            _require(getattr(self, name) in ("cpu", "gpu"), f"android.{name} must be cpu or gpu")
        _require(self.depth_input_size > 0, "android.depth_input_size must be positive")
        _require(self.depth_threads >= 1, "android.depth_threads must be at least 1")


@dataclass(frozen=True)
class Config:
    audio: AudioConfig
    pitch: PitchConfig
    pulse: PulseConfig
    colour: ColourConfig
    instruments: InstrumentsConfig
    spatial: SpatialConfig
    objects: ObjectsConfig
    camera: CameraConfig
    detection: DetectionConfig
    depth: DepthConfig
    tracking: TrackingConfig
    priority: PriorityConfig
    training: TrainingConfig
    study: StudyConfig
    android: AndroidConfig

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
    return _resolve_paths(config_from_dict(raw), config_path.resolve().parent)


def _resolve_paths(config: Config, base: Path) -> Config:
    """Make relative file paths relative to the config file, not the working directory."""

    def absolute(path: str) -> str:
        return str(path if Path(path).is_absolute() else base / path)

    detection = dataclasses.replace(
        config.detection, model_path=absolute(config.detection.model_path)
    )
    depth = dataclasses.replace(
        config.depth,
        model_path=absolute(config.depth.model_path),
        calibration_path=absolute(config.depth.calibration_path),
    )
    training = config.training
    if training.progress_path is not None:
        training = dataclasses.replace(training, progress_path=absolute(training.progress_path))
    study = dataclasses.replace(config.study, results_dir=absolute(config.study.results_dir))
    return dataclasses.replace(
        config, detection=detection, depth=depth, training=training, study=study
    )


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
    if origin is dict:
        if not isinstance(value, dict):
            raise ConfigError(f"{where} must be a mapping")
        key_type, value_type = typing.get_args(hint)
        return {
            _coerce(key_type, key, where): _coerce(value_type, item, f"{where}.{key}")
            for key, item in value.items()
        }
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
    if hint is bool and isinstance(value, bool):
        return value
    raise ConfigError(f"{where} must be {getattr(hint, '__name__', hint)}, got {value!r}")
