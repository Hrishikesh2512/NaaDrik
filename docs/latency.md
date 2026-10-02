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

End-to-end (frame capture → sound out) measurements arrive with the camera pipeline in v0.2.0.
