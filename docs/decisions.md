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

## 2026-10-02 · Black is silent (superseded in v0.4.1)

The brief specified black = silence, and v0.1.0 to v0.4.0 implemented it. A dark object right in
front of the user was inaudible; in live testing a person in dark clothing produced no sound.
Replaced by the presence layer below.

## 2026-10-02 · Pluck saturation

Karplus–Strong plucks have a crest factor near 8, so a lone red object hit the limiter while
bowed and flute notes did not. A `tanh` drive of 2 halves the crest factor and adds the bright
upper harmonics typical of a sitar.

## 2026-10-02 · Audio output runs under a watchdog

On the development machine, PortAudio's route through PipeWire to a hands-free Bluetooth
headset sometimes accepted a stream and then stopped pulling audio, which made blocking playback
hang forever. Output now uses a low-latency callback stream; start-up, stop and playback are
watched and a stall raises `AudioDeviceError` with guidance instead of freezing.

## 2026-10-02 · Detection with MediaPipe EfficientDet-Lite0

MediaPipe Tasks with EfficientDet-Lite0 (Apache-2.0) was preferred in the brief and runs in
≈30 ms at 320 px on a laptop CPU. Ultralytics YOLO was not considered because of its AGPL
licence. The same `.tflite` model runs on Android in Phase 2.

## 2026-10-02 · Depth via ONNX Runtime, not PyTorch

Depth Anything V2 Small runs from the `onnx-community` ONNX export on ONNX Runtime (CPU, about
17 MB installed) instead of PyTorch (gigabytes). Only the Small variant is Apache-2.0; Base and
Large are non-commercial and are deliberately not referenced. At 336×252 input it takes
≈100 ms alone and ≈170 ms while detection runs concurrently, so it runs on every 4th frame on its
own thread and the newest map is reused in between.

## 2026-10-02 · Distance: scene-relative by default, calibration optional

The model outputs relative inverse depth with an unknown scale and shift per frame, so metres
are not available. Two normalisations are offered:

* `scene` (default): an object's median disparity is placed between the frame's 5th and 95th
  percentiles. Needs no setup; "near" means "near compared with the rest of the view".
* `calibrated`: `naadrik calibrate` records the centre disparity of something at ~50 cm and
  something at ~3 m. More stable across scenes, but drifts if the model's scale changes a lot.

The result is quantised to near / mid / far (`depth.levels: 3`) with a hysteresis margin, so
depth noise at a boundary does not make the pulse rate flicker. Set `levels: 0` for continuous.
Distances are only fed to the tracker when a new depth map arrives, so the approach rate
reflects real change.

## 2026-10-02 · Colour: grey-world balance also normalises exposure

The grey-world correction scales each channel so the frame averages to mid grey. Besides
removing colour casts, this compensates exposure: without it a dim room made every object
quantise to "off" and fall silent. Brightness is therefore relative to the scene, similar to
human lightness constancy. Gains are clamped (0.5–4×) and smoothed across frames.

## 2026-10-02 · Tracking and selection stability

A lightweight IoU tracker (same label only) provides identity, smoothing and velocity. A track
must be seen in two frames before it can sound, which filters single-frame false positives, and
survives up to eight missed frames. The prioritiser keeps sounding objects unless a newcomer
beats the weakest by `switch_margin`, so voices do not swap back and forth between similar
objects.

## 2026-10-02 · Threads and the audio callback

Capture, detection and depth each have a thread; the audio callback is PortAudio's thread. The
perception side only swaps in a new target set; the callback creates, updates and releases
voices itself, so it never waits for perception. Live mode uses a 30 ms output buffer
(`audio.live_latency_s`) rather than the minimum, as headroom against Python thread contention;
no underflows were seen in testing.

## 2026-10-02 · Latency definition

End-to-end latency is measured from the moment a frame reaches the application to the moment
the audio block carrying its update reaches the DAC (PortAudio's DAC time). It excludes camera
exposure and USB transfer before the frame arrives, and any Bluetooth delay after the DAC. It
also excludes the musical delay until the next pulse onset, which depends on the pulse rate by
design.

## 2026-10-02 · Offline speech with eSpeak NG

eSpeak NG is small, fully offline, available in every Linux distribution, and fast (≈7 ms per
label, cached thereafter), so labels can be synthesised on the detection thread without a worker.
It is run as a subprocess, so its GPL licence does not affect Naadrik's. Its voice is robotic;
Piper (MIT) sounds far better but needs ~60 MB voice models, so it is a candidate for later.
Android has an offline system TTS for Phase 2.

## 2026-10-02 · Label first, then the sound

An announced object's voice is held until its label (plus `gap_s`) has finished, so the user
hears "red cup, left, near" and then the sound it describes, which is the pairing that teaches
the mapping. The label is spatialised at the object's azimuth, reinforcing direction, and other
voices are ducked by 12 dB for intelligibility. Labels wait until the object has a depth
estimate, otherwise every first label would say "mid distance".

## 2026-10-02 · Fading speech by probability, per announcement

The brief asks for speech that fades out over sessions. Each due announcement is spoken with a
probability that is 1 for the first three sessions and then falls linearly to 0 over five more.
Skipping individual announcements (rather than lowering the volume) keeps every spoken label
intelligible, and the user gets a mix of confirmed and unconfirmed objects, like a teacher
gradually stepping back. Session counts live in the user data directory, not the repository.

## 2026-10-02 · Spoken colour names

Each of the 27 quantised RGB combinations has a common colour name ("orange" is high red + low
green), so the spoken name always corresponds exactly to the instrument mix the user hears.

## 2026-10-02 · Study: what the vOICe-style baseline receives

The baseline sonifies an image, so each stimulus is drawn as a grey disc on black: position
from the grid, size from distance (the only distance cue an image has) and grey level from the
colour's luma, as a camera-to-greyscale pipeline would produce. Blue therefore renders dim
(luma 0.11) and quiet, which is faithful to the classic method rather than a handicap added
here; `greyscale: mean` is available as a fairer-to-blue variant. Parameters follow the classic
defaults: 1 s left-to-right sweep, 500–5000 Hz exponentially spaced rows, stereo pan with the
scan, a tick per sweep.

## 2026-10-02 · Study: protocol details

* Stimuli cycle through the whole grid before repeating, so a 27-trial test covers every
  position/height/distance cell once.
* Reaction time is measured from the end of the stimulus (playback blocks until then), which
  keeps it comparable between conditions.
* Each condition's results go to their own CSV plus a JSON with phase durations; rows are
  flushed per trial so an interrupted session keeps its data.
* Analysis uses Wilson intervals and one-sided binomial tests against chance with Holm
  correction, implemented with SciPy and NumPy rather than adding pandas. Pooling trials across
  participants is noted as a limitation in `docs/study.md`.
* Simulated participants (`oracle`, `random`) validate the pipeline; their ids carry a `sim-`
  prefix and the report flags them, so they cannot be mistaken for human data.

## 2026-10-02 · Presence layer: no detected object is ever silent (v0.4.1)

Every note now carries a soft neutral hum at the object's pitch, pulse and position, with the
colour instruments mixed on top. Black is the hum alone; white is the hum plus all three
instruments. Choices:

* **Pitched hum rather than plain noise.** Height is encoded by pitch, so the hum is a muted
  triangle at the note frequency. Some band-limited noise around the pitch gives it a texture
  unlike any colour instrument, and it has no vibrato or attack transient, so it is not mistaken
  for the flute.
* **Level 0.25, below the "low" colour level (0.35).** Loudness still orders brightness
  (black < dark colours < bright colours < white) and black is about 15 dB below a loud red:
  quiet but clearly present.
* **Zero is rejected.** The loader refuses `presence.level: 0`, so the safety property cannot be
  configured away by accident.
* **`master_gain` lowered from 0.8 to 0.75** so a single white object (four layers) stays below
  the limiter knee.

Study data recorded before v0.4.1 used the old mapping (black silent); do not pool it with later
sessions without noting the version (each session JSON records it).

## 2026-10-02 · Android: AudioTrack low-latency rather than Oboe

The brief allows Oboe (NDK) or AudioTrack in low-latency mode. AudioTrack with
`PERFORMANCE_MODE_LOW_LATENCY` and float PCM at the device's native rate and burst size gets the
same fast mixer path that Oboe's AAudio/OpenSL backends use; MMAP (Oboe's extra advantage) is not
offered on most mid-range phones, including the Galaxy A30s test device. Staying in Kotlin keeps
one engine implementation that is unit-tested on the JVM and needs no NDK. The output thread runs
at urgent-audio priority, starts with a two-burst buffer and grows it by one burst after any
underrun, the latency tuning Oboe applies. Latency is measured from AudioTrack DAC timestamps.

## 2026-10-02 · Android: one engine, one config, parity-tested

The Kotlin `core` module ports the Python sound engine line for line (instruments, presence hum,
note bank, voices, spatialiser, limiter). The app reads the same `config.yaml`, with the same
strict validation. A fixture of reference values exported from Python (mapping, ITD, head
shadow, limiter, plus later-milestone values such as priority and colour names) is checked by
the Kotlin tests to 1e-9, and a pytest fails if the fixture is stale. Notes are rendered at the
device's native sample rate so audio never passes through a resampler. Unlike the Python
version, voices mix the four layers (hum and three instruments) per sample from the note bank
instead of caching premixed notes, so the audio thread never allocates.

## 2026-10-02 · Android: Jetpack Compose UI

Compose gives semantic roles (headings, live regions, content descriptions) directly in code,
which suits a TalkBack-first app. All touch targets are at least 64 dp.

## 2026-10-02 · Interleaved pulses so equal objects do not fuse

Found in phone testing: two objects at the same height and distance, one left and one right,
were heard as a single sound in the centre. With the same pitch, timbre and pulse rate, and
onsets that coincide, the two signals are correlated enough to fuse into one phantom image, as a
mono recording does on two speakers.

When a voice starts while others sound at a similar rate (within a ratio of 1.25), its first
pulse is placed in the middle of the largest gap between their pulses: half a period after a
single other voice, a third or so between two. Onset asynchrony is among the strongest cues for
hearing separate sources, and the result is an audible left, right, left, right. Voices alone, or
at clearly different rates, still start immediately.

Increasing the interaural time or phase difference within each sound would not help: it already
follows the head's natural ITD (up to ~0.66 ms), which is what lateralises each sound, and larger
values sound diffuse rather than wider. The problem was between the two sources, not between the
ears. Implemented identically in Python and Kotlin.

## 2026-10-02 · Android depth: MiDaS v2.1 small (TFLite), ARCore probed

Depth Anything V2 Small, the desktop model, has no published TFLite export, and converting it
needs a TensorFlow toolchain; at ~100 MB it would also take over a second per frame on a mid-range
phone CPU. MiDaS v2.1 small (MIT, official Intel ISL release, 66 MB, 256x256) predicts the same
quantity, relative inverse depth, so the shared normalisation and near/mid/far quantiser apply
unchanged. It runs on the LiteRT GPU delegate where supported, otherwise on two CPU threads, on its
own thread every 4th frame.

ARCore's Depth API needs exclusive use of the camera, so using it means an ARCore-driven frame
source in place of CameraX. A2 probes whether the phone installs ARCore and supports depth, and
reports it; the ARCore frame source is built only once a test phone reports depth support.

## 2026-10-02 · Android detection: int8 EfficientDet-Lite0

The phone uses the int8 build of the desktop's detector (4.6 MB instead of 13.8 MB): same classes
and boxes, markedly faster on mobile CPUs.

## 2026-10-02 · Android: one APK per CPU family, portrait only

MediaPipe and LiteRT native libraries for all four ABIs added 78 MB; ABI splits produce separate
arm64-v8a and armeabi-v7a APKs (92 MB and 86 MB, mostly the depth model). The live screen is
locked to portrait: the phone is held upright or worn on the chest, and a rotation mid-session
would swap left and right.
