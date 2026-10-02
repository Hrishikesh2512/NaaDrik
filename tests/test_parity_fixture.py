import importlib.util
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def assert_close(actual: object, expected: object, path: str = "fixture") -> None:
    """Structural equality with a float tolerance: maths libraries differ in the last bit."""
    if isinstance(expected, float) or isinstance(actual, float):
        assert isinstance(actual, int | float) and isinstance(expected, int | float), path
        assert math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-12), (
            f"{path}: {actual} != {expected}. "
            "Android parity fixture is stale: run python scripts/export_parity_fixture.py"
        )
    elif isinstance(expected, list):
        assert isinstance(actual, list) and len(actual) == len(expected), path
        for i, (a, e) in enumerate(zip(actual, expected, strict=True)):
            assert_close(a, e, f"{path}[{i}]")
    elif isinstance(expected, dict):
        assert isinstance(actual, dict) and actual.keys() == expected.keys(), path
        for key in expected:
            assert_close(actual[key], expected[key], f"{path}.{key}")
    else:
        assert actual == expected, f"{path}: {actual!r} != {expected!r}"


def test_android_parity_fixture_is_current() -> None:
    spec = importlib.util.spec_from_file_location(
        "export", ROOT / "scripts/export_parity_fixture.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    committed = json.loads(module.FIXTURE.read_text())
    assert_close(json.loads(json.dumps(module.build_fixture())), committed)
