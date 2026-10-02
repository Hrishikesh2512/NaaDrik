import copy
from pathlib import Path

import pytest
import yaml

from naadrik.config import config_from_dict, load_config
from naadrik.errors import ConfigError

REPO_CONFIG = Path(__file__).resolve().parents[1] / "config.yaml"


@pytest.fixture
def raw_config() -> dict:
    return yaml.safe_load(REPO_CONFIG.read_text())


def test_repository_config_loads() -> None:
    config = load_config(REPO_CONFIG)
    assert config.objects.max_objects == 3
    assert config.pitch.scale == (0, 2, 4, 7, 9)
    assert isinstance(config.pulse.near_hz, float)


def test_missing_file_has_clear_message(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "nope.yaml")


def test_unknown_key_rejected(raw_config: dict) -> None:
    raw_config["pulse"]["near_hz_typo"] = 3
    with pytest.raises(ConfigError, match=r"config\.pulse: unknown key"):
        config_from_dict(raw_config)


def test_missing_key_rejected(raw_config: dict) -> None:
    del raw_config["colour"]["levels"]
    with pytest.raises(ConfigError, match="missing key"):
        config_from_dict(raw_config)


def test_wrong_type_rejected(raw_config: dict) -> None:
    raw_config["audio"]["sample_rate"] = "fast"
    with pytest.raises(ConfigError, match="sample_rate"):
        config_from_dict(raw_config)


@pytest.mark.parametrize(
    ("section", "key", "value"),
    [
        ("pulse", "far_hz", 20.0),
        ("colour", "thresholds", [0.7, 0.2]),
        ("spatial", "mode", "surround"),
        ("objects", "max_objects", 0),
    ],
)
def test_invalid_values_rejected(raw_config: dict, section: str, key: str, value: object) -> None:
    broken = copy.deepcopy(raw_config)
    broken[section][key] = value
    with pytest.raises(ConfigError):
        config_from_dict(broken)


def test_relative_paths_resolve_against_config_file(raw_config: dict, tmp_path: Path) -> None:
    (tmp_path / "custom.yaml").write_text(yaml.safe_dump(raw_config))
    config = load_config(tmp_path / "custom.yaml")
    assert Path(config.detection.model_path) == tmp_path / raw_config["detection"]["model_path"]
    assert Path(config.depth.calibration_path).parent == tmp_path


def test_class_importance_is_a_mapping(raw_config: dict) -> None:
    config = config_from_dict(raw_config)
    assert config.priority.class_importance["person"] == 1.0
    raw_config["priority"]["class_importance"]["person"] = "high"
    with pytest.raises(ConfigError, match=r"class_importance\.person"):
        config_from_dict(raw_config)
