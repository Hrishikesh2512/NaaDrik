# Changelog

All notable changes to Naadrik are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Fixed

- Android: the engine test crashed with "Unable to retrieve AudioTrack pointer" when reporting,
  because it read the audio track after releasing it.
- Two objects at the same height and distance fused into one centred sound; pulses of
  similar-rate voices are now interleaved (Python and Android).

### Changed

- Android demo: comparison scenarios play left alone, then right alone, then both.

## [1.0.0-alpha.1] - 2026-10-02

### Added

- Android project (`android/`, `com.naadrik.app`, minSdk 26, targetSdk 37) with a `core` Kotlin
  module and an `app` module.
- Kotlin port of the v0.4.1 sound engine: config loader with strict validation, mappings,
  synthesised instruments and presence hum, note bank, pulsed voices, spatialiser, soft limiter and
  live mixer; reads the shared `config.yaml`.
- Parity fixture exported from Python (`scripts/export_parity_fixture.py`) and Kotlin tests that
  match the Python mapping to 1e-9.
- Low-latency AudioTrack output at the device's native rate with underrun-driven buffer tuning
  and DAC-timestamp latency measurement.
- Demo screen with the listening scenarios and a 10 s engine test that reports render cost,
  underruns and latency; accessible labels, live-region status and 64 dp touch targets.
- Android job in CI (ktlint, unit tests, Android lint, debug build).

## [0.4.1] - 2026-10-02

### Fixed

- Safety: dark and black objects were silent. Every object now has a presence layer, a soft
  neutral hum at its pitch, pulse rate and 3D position, with the colour instruments mixed on top.
  Black plays the hum alone; white plays the hum plus all three instruments loud.

### Added

- `instruments.presence` in `config.yaml` (`level`, `cutoff_ratio`, `noise`); a level of 0 is
  rejected so the safety property cannot be switched off by accident.
- `black-vs-white` demo scenario.

### Changed

- `audio.master_gain` 0.8 → 0.75 to keep a single white object below the limiter knee.
- Study training instructions for the Naadrik condition mention the presence hum.

## [0.4.0] - 2026-10-02

### Added

- `naadrik study`: evaluation with synthetic stimuli on a 3×3×3 grid (side × height ×
  distance) plus a colour set, in baseline (no explanation), training (feedback and replay) and
  test (no feedback) phases; single-key responses, replays and reaction times.
- Baseline sonifier modelled on the classic vOICe mapping (greyscale image, 1 s left-to-right
  sweep, row → frequency, brightness → loudness, stereo pan) for comparison.
- Per-trial CSV (stimulus, responses, correctness per axis, reaction times, replays) and a
  session JSON with phase durations; crash-safe incremental writes.
- `naadrik analyse`: accuracy per axis and overall vs chance with Wilson intervals, binomial
  tests and Holm correction, training time, mean response time, a Markdown report and charts.
- Simulated participants for validating the protocol and analysis.
- `docs/study.md` with instructions for running sessions.

## [0.3.0] - 2026-10-02

### Added

- `naadrik train`: training mode that speaks a label such as "red cup, left, near" before an
  object's sound, live with the camera or with synthetic objects (`--no-camera`).
- Offline text-to-speech through eSpeak NG, cached, spatialised at the object's direction.
- Announcements hold the object's voice until the label has been spoken and duck other voices.
- Speech fade-out across sessions: full speech for three sessions, then a linear fade over
  five; progress stored in the user data directory, with `--reset-progress` and `--always-speak`.
- Names for all 27 quantised colours.
- Synthetic 3×3×3 grid stimuli shared with the upcoming study mode.

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
