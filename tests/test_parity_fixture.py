import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_android_parity_fixture_is_current() -> None:
    spec = importlib.util.spec_from_file_location(
        "export", ROOT / "scripts/export_parity_fixture.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    committed = json.loads(module.FIXTURE.read_text())
    assert committed == json.loads(
        json.dumps(module.build_fixture())
    ), "Android parity fixture is stale: run python scripts/export_parity_fixture.py"
