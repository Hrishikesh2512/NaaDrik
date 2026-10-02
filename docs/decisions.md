# Design decisions

Each entry records a choice where the brief left room for judgement.

## 2026-10-02 · Coordinate and value conventions

`render_object(x, y, distance, r, g, b)` takes normalised values: `x`, `y` in [0, 1] with the
origin at the top-left (matching detector box coordinates), `distance` in [0, 1] from near to
far, and colour channels in [0, 1]. Calibrating depth into this range is the depth module's job,
so the sound engine never sees metres or raw model output.

## 2026-10-02 · Pre-rendered note bank

Because pitch is quantised to a 13-note pentatonic scale, every instrument note is rendered once
at start-up (13 notes × 3 instruments, ~0.5 s). The real-time path only gates, mixes and
spatialises arrays, which keeps three voices at ~5% of the audio block budget in plain NumPy.
The cost is that pitch changes take effect at the next pulse rather than mid-note, which is
also musically cleaner.

## 2026-10-02 · Pulse rate is log-interpolated

Rate = `near_hz × (far_hz / near_hz) ^ distance`. Rate perception is roughly logarithmic, so equal
steps in distance give equal-feeling steps in tempo (1 → 2.8 → 8 Hz at 0, 0.5, 1).

## 2026-10-02 · Gated pulses with a capped gate

Each pulse sounds a note for `duty_cycle` of the period, capped at `max_gate_s` (0.35 s), then
releases. Without the cap a far object at 1 Hz would drone for half a second each beat, which
masks nearer objects.

## 2026-10-02 · Spatialisation: spherical-head model instead of measured HRTFs

Measured HRTFs need SOFA files and a convolution engine, and generic HRTFs often lateralise no
better than a good structural model for people they were not measured on. The Brown–Duda
spherical-head model (Woodworth ITD + first-order head-shadow filter per ear) costs two IIR taps
per ear and gives clear left/right cues. Two adjustments for this use:

* **Power-normalised head shadow.** The raw model makes a lateral source up to 6 dB louder than a
  centred one. Loudness is reserved for brightness, so the per-ear high-frequency gains are scaled
  to keep total power constant across azimuth, preserving only the interaural ratio.
* **Extra broadband ILD (`extra_ild_db`, 9 dB at 90°).** The head-shadow model has no level
  difference at low frequencies, so a low flute note lateralised far less than a high sitar note
  (6 dB vs 14 dB at the frame edge). The extra ILD makes position consistent across timbres.

Front/back is supported in the API (azimuth beyond ±90° folds the ITD and adds a rear low-pass),
but a forward-facing camera only produces frontal azimuths. Android's Spatializer API with head
tracking replaces this on supported devices in Phase 2. `mode: pan` (ITD + constant-power pan)
is kept as a cheaper fallback.

## 2026-10-02 · Frame edges map to ±80° azimuth

A typical webcam sees about ±35°. Mapping that faithfully would squeeze every object into a
narrow frontal arc where headphone localisation is weakest. Exaggerating to ±80° trades
geometric truth for discriminability; it is configurable (`max_azimuth_deg`).

## 2026-10-02 · Black is silent

The brief specifies black = silence and that is implemented. It means a dark object right in
front of the user is inaudible. This is a safety concern for real-world use and should be
revisited after the study (for example, a quiet presence tone for close objects).

## 2026-10-02 · Pluck saturation

Karplus–Strong plucks have a crest factor near 8, so a lone red object hit the limiter while
bowed and flute notes did not. A `tanh` drive of 2 halves the crest factor and adds the bright
upper harmonics typical of a sitar.

## 2026-10-02 · Audio output runs under a watchdog

On the development machine, PortAudio's route through PipeWire to a hands-free Bluetooth
headset sometimes accepted a stream and then stopped pulling audio, which made blocking playback
hang forever. Output now uses a low-latency callback stream; start-up, stop and playback are
watched and a stall raises `AudioDeviceError` with guidance instead of freezing.
