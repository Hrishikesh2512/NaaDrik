# Sound-mapping rationale

Naadrik gives each object a single sound in which every property has its own perceptual
dimension, so properties can be heard at the same time without interfering.

| Property | Dimension | Why this dimension |
|---|---|---|
| Horizontal position | Spatial position (ITD + ILD) | Direction is what the auditory system localises natively; no learning needed. |
| Height | Pitch | "High = high pitch" is a strong cross-modal association, even in congenitally blind listeners. |
| Distance | Pulse rate | Tempo is independent of pitch, timbre and position. Volume is avoided because loudness is already used for brightness and is unreliable (device volume, hearing loss, masking). Faster = closer matches parking sensors, which many users already know. |
| Colour | Timbre (instrument mix) | Timbre is a separate perceptual dimension from pitch and tempo. Three instruments map to the three RGB channels, so mixtures are heard as mixtures. |
| Brightness | Loudness | Falls out of the RGB mix for free: more colour energy, more sound. |

## Pitch

* Major pentatonic scale (`[0, 2, 4, 7, 9]`) from G3 (196 Hz) over 2.5 octaves: 13 notes.
  The pentatonic scale has no semitone clashes, so any three objects sound consonant together.
* Vertical position is quantised to the nearest scale degree. Quantising also makes heights
  easier to label ("three steps up") than a continuous glide.

## Distance

* 0 (nearest) → 8 Hz, 1 (farthest) → 1 Hz, log-interpolated.
* Each pulse gates a note for half the period, capped at 0.35 s, with a 2 ms attack and 25 ms
  release.

## Colour

| Channel | Instrument | Synthesis |
|---|---|---|
| Red | Plucked string (sitar-like) | Karplus–Strong string as a single IIR, one-sided clipping for the jawari bridge buzz, an octave sympathetic string and soft saturation |
| Green | Bowed string (violin-like) | Band-limited additive sawtooth, delayed vibrato, three body resonances, a little bow noise |
| Blue | Flute | Fundamental plus two weak harmonics, breath noise, onset chiff, light vibrato and tremolo |

Each channel is quantised to off (< 0.25), low (< 0.6) or high, with gains 0, 0.35 (≈ −9 dB)
and 1. Three levels are few enough to learn and still distinguish, for example, red from orange
(red + low green) from yellow (red + high green).

### Presence layer

Every note also contains a **presence hum**: a muted triangle wave at the note's pitch, low-passed
at 2.5× the pitch, blended with soft noise band-limited around the pitch. It is mixed in at
`instruments.presence.level` (0.25, about 12 dB below a "high" instrument and below a "low"
one), so black objects are audible and still carry pitch, pulse rate and position, while every
colour remains louder than black. It has no vibrato, attack transient or breath, so it does not
read as one of the colour instruments. The level must be greater than zero; the config loader
rejects 0 because a silent object is a safety risk.

| Colour | What plays |
|---|---|
| Black | presence hum only (≈ −15 dB relative to red) |
| Dark red | hum + quiet sitar |
| Red | hum + loud sitar |
| White | hum + all three instruments loud |

Notes are loudness-matched (RMS over the first 0.3 s) before the per-instrument gain, so equal
colour levels sound roughly equally loud across instruments.

## Mixing

Up to three voices are summed, multiplied by `master_gain` and passed through a soft limiter
(linear below 0.8, `tanh` shoulder above), so dense scenes never clip harshly. A single object,
white included, stays below the limiter knee (`master_gain` 0.75).

## Open questions for the study

* Whether ±80° azimuth exaggeration helps or confuses when combined with a narrow camera.
* Whether three colour levels are discriminable for all three instruments at all pitches.
* Whether pulse rates above ~6 Hz remain countable when three objects play together.
