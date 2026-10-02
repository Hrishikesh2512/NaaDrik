from pathlib import Path

import pytest

from naadrik.config import Config, load_config

REPO_CONFIG = Path(__file__).resolve().parents[1] / "config.yaml"


@pytest.fixture(scope="session")
def config() -> Config:
    return load_config(REPO_CONFIG)
