"""Camera-free training: synthetic objects, each announced and then sounded."""

from __future__ import annotations

import random
import time

from naadrik.audio_output import AudioOutput
from naadrik.config import Config
from naadrik.sound_engine import SoundEngine
from naadrik.sound_engine.mixer import LiveMixer
from naadrik.speech import Speaker
from naadrik.stimuli import sample
from naadrik.training.describe import describe

_LABELS = ("cup", "ball", "box", "bottle", "chair", "bag")
_SOUND_S = 3.0
_PAUSE_S = 0.8


def make_mixer(engine: SoundEngine, config: Config) -> LiveMixer:
    training = config.training
    return LiveMixer(
        engine,
        duck_db=training.duck_db,
        gap_s=training.gap_s,
        spatialise_speech=training.spatialise_speech,
    )


def run_scripted_training(
    config: Config,
    speaker: Speaker | None,
    probability: float,
    trials: int,
    device: str | int | None,
    rng: random.Random | None = None,
) -> list[str]:
    rng = rng or random.Random()
    engine = SoundEngine(config)
    mixer = make_mixer(engine, config)
    audio = AudioOutput(
        mixer.render,
        engine.sample_rate,
        config.audio.block_size,
        device,
        latency=config.audio.live_latency_s,
    )
    spoken: list[str] = []
    audio.start()
    try:
        for trial, stimulus in enumerate(sample(trials, rng), start=1):
            label = rng.choice(_LABELS)
            state = stimulus.state()
            text = describe(label, state, config)
            announce = speaker is not None and rng.random() < probability
            clip = speaker.say(text) if announce and speaker is not None else None
            print(f"{trial:3}/{trials}  {text if announce else '(listen)'}", flush=True)
            mixer.update(
                {trial: state}, time.perf_counter(), {trial: clip} if clip is not None else None
            )
            if clip is not None:
                spoken.append(text)
                time.sleep(len(clip) / engine.sample_rate + config.training.gap_s)
            time.sleep(_SOUND_S)
            mixer.update({}, time.perf_counter())
            time.sleep(_PAUSE_S)
            if audio.error is not None:
                raise audio.error
    finally:
        audio.stop()
    return spoken
