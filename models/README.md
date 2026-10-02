# Models

Model files are not committed. Fetch them once with:

```bash
naadrik models download
```

| File | Model | Licence | Source |
|---|---|---|---|
| `efficientdet_lite0.tflite` | EfficientDet-Lite0, COCO (MediaPipe Tasks object detector) | Apache-2.0 | storage.googleapis.com/mediapipe-models |
| `depth_anything_v2_small.onnx` | Depth Anything V2 Small, relative depth | Apache-2.0 | huggingface.co/onnx-community/depth-anything-v2-small |

Checksums are verified after download. Only the Small Depth Anything V2 variant is
Apache-2.0; the Base and Large variants are CC-BY-NC-4.0 and must not be used.
