"""Model registry and one-time download. Models run fully offline once downloaded."""

from __future__ import annotations

import hashlib
import logging
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from naadrik.config import Config
from naadrik.errors import ModelNotFoundError

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ModelSpec:
    name: str
    url: str
    sha256: str
    licence: str


DETECTOR = ModelSpec(
    name="EfficientDet-Lite0 (MediaPipe object detector, COCO)",
    url="https://storage.googleapis.com/mediapipe-models/object_detector/"
    "efficientdet_lite0/float32/latest/efficientdet_lite0.tflite",
    sha256="40338edf5ec70d43e318b0a716a84d4564cd1802759a7a07170c7e43796dbf58",
    licence="Apache-2.0",
)
DEPTH = ModelSpec(
    name="Depth Anything V2 Small (ONNX)",
    url="https://huggingface.co/onnx-community/depth-anything-v2-small/resolve/main/onnx/model.onnx",
    sha256="afb6a5c28f3b6bf1618c6e43f02073ef9dfdc70e937502d51603e57b0a1df10c",
    licence="Apache-2.0",
)


def required_models(config: Config) -> list[tuple[ModelSpec, Path]]:
    return [
        (DETECTOR, Path(config.detection.model_path)),
        (DEPTH, Path(config.depth.model_path)),
    ]


def require_model(path: str | Path, spec: ModelSpec) -> Path:
    path = Path(path)
    if not path.is_file():
        raise ModelNotFoundError(
            f"{spec.name} not found at {path}. Run `naadrik models download` once to fetch it."
        )
    return path


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(spec: ModelSpec, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix + ".part")
    log.info("downloading %s", spec.name)
    try:
        urllib.request.urlretrieve(spec.url, partial)
    except OSError as exc:
        partial.unlink(missing_ok=True)
        raise ModelNotFoundError(f"Could not download {spec.name} from {spec.url}: {exc}") from exc
    actual = sha256_of(partial)
    if actual != spec.sha256:
        partial.unlink(missing_ok=True)
        raise ModelNotFoundError(
            f"Checksum mismatch for {spec.name}: expected {spec.sha256}, got {actual}."
        )
    partial.replace(destination)
    return destination


def model_status(config: Config) -> list[tuple[ModelSpec, Path, str]]:
    rows = []
    for spec, path in required_models(config):
        if not path.is_file():
            state = "missing"
        elif sha256_of(path) != spec.sha256:
            state = "present (checksum differs: custom or corrupted)"
        else:
            state = "ok"
        rows.append((spec, path, state))
    return rows
