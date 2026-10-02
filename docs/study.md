# Study mode

Study mode measures how well people can read object properties from sound, with Naadrik and
with a classic baseline mapping, using synthetic stimuli. No camera is needed.

## Design

* **Stimuli.** One object per trial on a 3 × 3 × 3 grid: side (left / centre / right) ×
  height (high / middle / low) × distance (near / mid / far), in one of the colours listed in
  `study.colours` (default red, green, blue, yellow, white). Trials cycle through the grid in
  random order so every cell is used once before any repeats.
* **Conditions.**
  * `naadrik`: the Naadrik mapping (`render_object`), 3 s per stimulus.
  * `voice`: a baseline modelled on the classic vOICe mapping. The object is drawn as a grey
    disc on black (size from distance: near large, far small; grey level from the colour's
    luma), and the image is scanned left to right once a second: rows are sines from 500 Hz
    (bottom) to 5000 Hz (top), brightness is loudness, the scan pans left to right, and a tick
    marks each sweep. It carries no colour beyond grey level and no distance beyond size.
* **Phases** (per condition):
  1. **Baseline** (9 trials): no explanation, no feedback. Measures how intuitive the mapping is.
  2. **Training** (27 trials): the mapping is explained; after each answer the correct answer
     is shown per axis and the stimulus is replayed.
  3. **Test** (27 trials): no feedback.
* **Responses.** After each stimulus the participant answers side, height, distance and
  colour with single keys (shown on screen); space replays the stimulus. Reaction times are
  measured from the end of the stimulus.

## Running a session

Use headphones and a quiet room. Set the system volume once with `naadrik demo` and keep it.

```bash
naadrik study --participant P01                         # both conditions, Naadrik first
naadrik study --participant P02 --order voice-first     # alternate order across participants
naadrik study --participant P03 --condition naadrik     # one condition only
naadrik study --participant P04 --phases test           # e.g. a later re-test
```

Counterbalance: odd-numbered participants `--order naadrik-first`, even `--order voice-first`.
A full session for both conditions is about 2 × 63 trials and takes 30–45 minutes; offer a break
between conditions. Ctrl-C stops at any time; completed trials are already on disk.

The participant reads (or has read to them) the instructions printed at the start of each phase.
The terminal works with screen readers; answers are single keys.

## Output

Each condition writes two files to `results/` (configurable `study.results_dir`):

* `<participant>_<condition>_<UTC timestamp>.csv`: one row per trial with the stimulus
  (`side, height, distance, colour`), responses (`resp_*`), correctness per axis
  (`correct_*`), `all_correct`, `rt_first_s` (end of stimulus to first answer), `rt_total_s`
  (to last answer), `replays` and a timestamp. Rows are flushed as they are written.
* `<…>.json`: participant, condition, Naadrik version, colours, stimulus length and per-phase
  trial counts and durations (the training time).

## Analysis

```bash
naadrik analyse                       # everything in results/
naadrik analyse results/P01_* --out results/P01-report
```

This writes `report.md` and charts to `results/report/`:

* accuracy per axis and for all four axes together, per condition and phase, with 95% Wilson
  intervals, the chance level, a one-sided binomial test against chance and Holm-corrected
  p-values across the table;
* mean axis accuracy and mean response time per phase;
* mean training time per condition;
* `accuracy_test.png`, `accuracy_baseline.png`: accuracy per axis vs chance;
* `learning_curve.png`: rolling mean accuracy across all trials, phases marked.

Chance is 1/3 for side, height and distance, 1/(number of colours) for colour, and their
product for all four correct (0.74% with five colours).

Trials are pooled across participants; the binomial test treats trials as independent, which
overstates certainty when participants differ. For a publishable comparison, fit a mixed model
(participant as a random effect) to the CSVs.

## Validating the setup without people

Simulated participants check the protocol and analysis end to end; their ids start with `sim-`
and the report flags them:

```bash
naadrik study --participant X --simulate random   # should land at chance
naadrik study --participant X --simulate oracle   # should be 100%
naadrik analyse
```
