"""Object detection with MediaPipe Tasks (EfficientDet-Lite0, COCO classes)."""

from __future__ import annotations

import numpy as np

from naadrik.config import DetectionConfig
from naadrik.errors import ModelNotFoundError
from naadrik.models import DETECTOR, require_model
from naadrik.scene import Box, Detection


class ObjectDetector:
    def __init__(self, cfg: DetectionConfig) -> None:
        path = require_model(cfg.model_path, DETECTOR)
        # Imported here: MediaPipe takes about a second to import and is only needed live.
        import mediapipe as mp
        from mediapipe.tasks.python import BaseOptions, vision

        self._mp = mp
        options = vision.ObjectDetectorOptions(
            base_options=BaseOptions(model_asset_path=str(path)),
            running_mode=vision.RunningMode.IMAGE,
            max_results=cfg.max_results,
            score_threshold=cfg.score_threshold,
        )
        try:
            self._detector = vision.ObjectDetector.create_from_options(options)
        except (RuntimeError, ValueError) as exc:
            raise ModelNotFoundError(f"Could not load detector model {path}: {exc}") from exc

    def detect(self, image_rgb: np.ndarray) -> list[Detection]:
        height, width = image_rgb.shape[:2]
        image = self._mp.Image(
            image_format=self._mp.ImageFormat.SRGB, data=np.ascontiguousarray(image_rgb)
        )
        result = self._detector.detect(image)
        detections = []
        for item in result.detections:
            category = item.categories[0]
            bbox = item.bounding_box
            box = Box(
                bbox.origin_x / width,
                bbox.origin_y / height,
                (bbox.origin_x + bbox.width) / width,
                (bbox.origin_y + bbox.height) / height,
            )
            detections.append(Detection(box, category.category_name or "object", category.score))
        return detections

    def close(self) -> None:
        self._detector.close()
