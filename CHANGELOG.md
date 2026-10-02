# Changelog

All notable changes to Naadrik are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.2.0] - 2026-10-02

### Added

- `naadrik live`: real-time webcam sonification with separate capture, detection, depth and
  audio threads.
- Object detection with MediaPipe EfficientDet-Lite0 (Apache-2.0).
- Monocular depth with Depth Anything V2 Small on ONNX Runtime, run every Nth frame; median box
  disparity normalised against the scene or a calibration, quantised to near / mid / far with
  hysteresis.
- `naadrik calibrate` to record near and far depth references.
- Per-object colour from the median of the box centre with grey-world white balance and
  exposure normalisation.
- IoU tracker with smoothed position, velocity, distance, approach rate and colour so sounds
  glide between frames.
- Prioritiser scoring closeness × class importance × centredness with a motion boost and a
  sticky top-3 selection.
- Live mixer that creates, updates and releases voices on the audio thread.
- End-to-end and per-stage latency measurement, logged and shown in the debug window.
- Debug window with boxes, depth view, colour swatches and per-object sound parameters.
- `naadrik models` to check and download models with checksum verification.

### Fixed

- Qt font and Wayland warnings from the OpenCV wheel's bundled Qt.

## [0.1.0] - 2026-10-02

### Added

- Sound engine with `SoundEngine.render_object(x, y, distance, r, g, b)` returning a spatialised
  stereo buffer, plus scene and moving-path rendering.
- Mappings: horizontal position → azimuth, height → pentatonic pitch (13 notes over 2.5 octaves),
  distance → log-interpolated pulse rate (8 Hz near to 1 Hz far), RGB → three-level
  instrument mix.
- Synthesised instruments with no samples: Karplus–Strong sitar-like pluck with bridge buzz and a
  sympathetic string, additive bowed string with vibrato and body resonances, flute with breath
  and chiff.
- Pre-rendered note bank so the real-time path is gating, mixing and filtering only.
- Streaming binaural spatialiser: Woodworth ITD and a power-normalised Brown–Duda head-shadow
  filter, with a constant-power pan fallback and gliding parameters.
- Pulsed voices with gated notes, gliding azimuth and pulse rate, and a soft limiter on the mix.
- Low-latency callback audio output with a watchdog that reports stalled devices.
- `naadrik demo` with 14 listening scenarios, WAV export and `--device` selection;
  `naadrik devices`.
- Typed `config.yaml` with strict validation of every mapping parameter.
- Tests for the mappings, instruments, spatialiser, engine and audio output; CI with ruff, black
  and pytest on Python 3.11 to 3.13.
- Documentation: README, contributing guide, design decisions, sound-mapping rationale, latency.
