from pathlib import Path

import pytest

from naadrik.errors import ModelNotFoundError
from naadrik.models import DEPTH, require_model, sha256_of


def test_missing_model_message_tells_user_how_to_fix(tmp_path: Path) -> None:
    with pytest.raises(ModelNotFoundError, match="naadrik models download"):
        require_model(tmp_path / "absent.onnx", DEPTH)


def test_sha256(tmp_path: Path) -> None:
    path = tmp_path / "x"
    path.write_bytes(b"naadrik")
    assert sha256_of(path) == "77c4df48e4eed5d3d75bdbbda39fd78f3a1fa2328d981c72587f82e42c3eab6e"
