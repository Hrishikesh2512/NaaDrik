# Latency measurements

## Audio path (v0.1.0)

Measured on the development laptop (Fedora 44, Python 3.14, Intel HDA ALC256, PortAudio 19.7
via ALSA), 48 kHz, 256-frame blocks.

| Stage | Time |
|---|---|
| Rendering 3 voices for one 256-frame block (5.33 ms of audio) | 0.26 ms (≈ 5% of budget) |
| Note bank build at start-up | 0.47 s |
| PortAudio output latency, `latency="low"`, built-in audio (hw:0,0) | 10.7 ms |
| PortAudio output latency, default route via PipeWire | 10.7 ms reported; stream start ≈ 1.5 s |
| Underflows over a 3 s run, built-in audio | 0 |

The default route on that machine pointed at a Bluetooth headset in hands-free mode, which
stalled after one or two callbacks. Bluetooth A2DP adds roughly 100–200 ms on its own, so wired
or low-latency earbuds are needed to meet the end-to-end target.

## Live pipeline (v0.2.0)

Same laptop (Intel Core i5-13450HX, 16 threads, CPU only), built-in webcam at 640×480 resized
to 320×240, audio on the built-in device with a 30 ms output buffer, 45 s run, defaults from
`config.yaml`. See `docs/decisions.md` for exactly what "end to end" covers.

| Stage | Mean | p95 |
|---|---|---|
| Detection (EfficientDet-Lite0, 320×240) | 33 ms | 42 ms |
| Depth (Depth Anything V2 Small, 336×252, every 4th frame, own thread) | 174 ms | 188 ms |
| Frame arrival → mixer update | 34 ms | 44 ms |
| **Frame arrival → sound at DAC (end to end)** | **71 ms** | **81 ms** |
| Audio underflows | 0 | |

Notes:

* The webcam delivered 10–20 fps: in dim light it lengthens exposure and drops its frame rate,
  which adds up to ~100 ms before a frame reaches the app. Good lighting matters more than any
  software setting here.
* Depth latency does not add to the end-to-end figure because sound is driven by detection on
  every frame; depth only refreshes distances (≈ every 200–400 ms at these frame rates).
* With a 10.7 ms output buffer the audio itself adds ~11 ms; the 30 ms live buffer adds ~32 ms in
  exchange for robustness. Both are configurable.
