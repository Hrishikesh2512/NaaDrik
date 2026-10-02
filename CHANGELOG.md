# Changelog

All notable changes to Naadrik are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

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
