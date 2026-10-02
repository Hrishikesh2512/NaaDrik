"""Monocular relative depth with Depth Anything V2 Small via ONNX Runtime."""

from __future__ import annotations

import cv2
import numpy as np

from naadrik.config import DepthConfig
from naadrik.errors import ModelNotFoundError
from naadrik.models import DEPTH, require_model

_PATCH = 14
_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


class DepthEstimator:
    def __init__(self, cfg: DepthConfig) -> None:
        path = require_model(cfg.model_path, DEPTH)
        import onnxruntime as ort

        options = ort.SessionOptions()
        options.intra_op_num_threads = cfg.threads
        options.log_severity_level = 3
        try:
            self._session = ort.InferenceSession(
                str(path), sess_options=options, providers=["CPUExecutionProvider"]
            )
        except Exception as exc:  # onnxruntime raises its own exception hierarchy
            raise ModelNotFoundError(f"Could not load depth model {path}: {exc}") from exc
        self._input = self._session.get_inputs()[0].name
        self._width = cfg.input_width

    def input_size(self, frame_height: int, frame_width: int) -> tuple[int, int]:
        """Model input (height, width): fixed width, aspect-preserving height, multiples of 14."""
        height = max(_PATCH, round(frame_height * self._width / frame_width / _PATCH) * _PATCH)
        return height, self._width

    def estimate(self, image_rgb: np.ndarray) -> np.ndarray:
        """Relative disparity map at model resolution: larger values are nearer."""
        height, width = self.input_size(*image_rgb.shape[:2])
        resized = cv2.resize(image_rgb, (width, height), interpolation=cv2.INTER_LINEAR)
        tensor = ((resized.astype(np.float32) / 255.0 - _MEAN) / _STD).transpose(2, 0, 1)[None]
        output = self._session.run(None, {self._input: tensor})[0]
        return output[0].astype(np.float32)
