import dataclasses
import random
import shutil
import struct
from pathlib import Path

import numpy as np
import pytest

from naadrik.config import Config
from naadrik.errors import ConfigError, SpeechError
from naadrik.sound_engine import ObjectState, SoundEngine
from naadrik.sound_engine.mixer import LiveMixer
from naadrik.speech import Speaker, parse_wav, trim_silence
from naadrik.stimuli import COLOURS, full_grid, sample
from naadrik.training.coach import Candidate, TrainingCoach
from naadrik.training.describe import COLOUR_NAMES, colour_name, describe
from naadrik.training.progress import TrainingProgress, speech_probability

# --- Descriptions ----------------------------------------------------------------------


def test_describe_matches_brief_example(config: Config) -> None:
    state = ObjectState(x=0.1, y=0.5, distance=0.0, r=0.9, g=0.1, b=0.1)
    assert describe("cup", state, config) == "red cup, left, near"


def test_describe_with_height(config: Config) -> None:
    training = dataclasses.replace(config.training, include_height=True)
    cfg = dataclasses.replace(config, training=training)
    state = ObjectState(x=0.9, y=0.1, distance=1.0, r=0, g=0, b=1)
    assert describe("ball", state, cfg) == "blue ball, right, high, far"


def test_every_quantised_colour_has_a_unique_name() -> None:
    assert len(COLOUR_NAMES) == 27
    assert len(set(COLOUR_NAMES.values())) == 27


@pytest.mark.parametrize(
    ("rgb", "name"),
    [
        ((1, 1, 0), "yellow"),
        ((1, 0.4, 0), "orange"),
        ((0.4, 0.4, 0.4), "grey"),
        ((0, 0, 0), "black"),
    ],
)
def test_colour_names(config: Config, rgb: tuple[float, float, float], name: str) -> None:
    assert colour_name(*rgb, config) == name


# --- Fade-out schedule and progress ----------------------------------------------------


def test_speech_fades_out_over_sessions(config: Config) -> None:
    cfg = config.training
    full, fade = cfg.full_speech_sessions, cfg.fade_sessions
    probabilities = [speech_probability(s, cfg) for s in range(1, full + fade + 3)]
    assert probabilities[:full] == [1.0] * full
    fading = probabilities[full : full + fade]
    assert all(0.0 < p < 1.0 for p in fading)
    assert np.all(np.diff(fading) < 0)
    assert probabilities[-1] == 0.0


def test_progress_persists_and_resets(config: Config, tmp_path: Path) -> None:
    cfg = dataclasses.replace(config.training, progress_path=str(tmp_path / "p" / "t.yaml"))
    progress = TrainingProgress.load(cfg)
    assert progress.start_session() == 1
    assert progress.start_session() == 2
    assert TrainingProgress.load(cfg).sessions == 2
    progress.reset()
    assert TrainingProgress.load(cfg).sessions == 0


def test_malformed_progress_is_explained(config: Config, tmp_path: Path) -> None:
    path = tmp_path / "t.yaml"
    path.write_text("sessions: [1, 2")
    cfg = dataclasses.replace(config.training, progress_path=str(path))
    with pytest.raises(ConfigError, match="reset-progress"):
        TrainingProgress.load(cfg)


# --- Coach -----------------------------------------------------------------------------


def fake_say(text: str) -> np.ndarray:
    return np.full(len(text), 0.1, dtype=np.float32)


RED_CUP = Candidate(1, "cup", ObjectState(0.1, 0.5, 0.0, 1, 0, 0))


def test_coach_announces_new_objects_then_repeats(config: Config) -> None:
    coach = TrainingCoach(config, fake_say, probability=1.0)
    assert list(coach.announcements([RED_CUP], now=0.0)) == [1]
    assert coach.announcements([RED_CUP], now=1.0) == {}
    assert list(coach.announcements([RED_CUP], now=config.training.repeat_s + 0.1)) == [1]
    assert coach.spoken == ["red cup, left, near"] * 2


def test_coach_with_zero_probability_is_silent(config: Config) -> None:
    coach = TrainingCoach(config, fake_say, probability=0.0)
    assert coach.announcements([RED_CUP], now=0.0) == {}


def test_coach_probability_thins_announcements(config: Config) -> None:
    coach = TrainingCoach(config, fake_say, probability=0.3, rng=random.Random(1))
    candidates = [Candidate(i, "cup", RED_CUP.state) for i in range(1000)]
    assert 0.2 < len(coach.announcements(candidates, now=0.0)) / 1000 < 0.4


# --- Mixer announcements ---------------------------------------------------------------


@pytest.fixture(scope="module")
def engine(config: Config) -> SoundEngine:
    return SoundEngine(config)


def run_blocks(mixer: LiveMixer, blocks: int) -> np.ndarray:
    return np.concatenate([mixer.render(256) for _ in range(blocks)])


def test_announced_voice_waits_for_its_label(engine: SoundEngine) -> None:
    mixer = LiveMixer(engine, gap_s=0.0)
    speech = np.zeros(256 * 10, dtype=np.float32)  # silent "speech" so only the voice is heard
    mixer.update({1: ObjectState(0.5, 0.5, 0.0, 1, 0, 0)}, 0.0, {1: speech})
    during = run_blocks(mixer, 10)
    assert not np.any(during)
    after = run_blocks(mixer, 20)
    assert np.any(after)
    assert not mixer.speaking


def test_other_voices_duck_while_speaking(engine: SoundEngine) -> None:
    blue = ObjectState(0.5, 0.5, 0.0, 0, 0, 1)
    plain = LiveMixer(engine)
    plain.update({2: blue}, 0.0)
    ducked = LiveMixer(engine, duck_db=12.0)
    ducked.update({2: blue, 1: blue}, 0.0, {1: np.zeros(256 * 40, dtype=np.float32)})
    level_plain = np.abs(run_blocks(plain, 40)[2560:]).max()
    level_ducked = np.abs(run_blocks(ducked, 40)[2560:]).max()
    assert level_ducked == pytest.approx(level_plain * 10 ** (-12 / 20), rel=0.05)


def test_speech_is_dropped_when_object_leaves(engine: SoundEngine) -> None:
    mixer = LiveMixer(engine)
    mixer.update({1: ObjectState(0.5, 0.5, 0.0, 1, 0, 0)}, 0.0, {1: np.ones(48000, np.float32)})
    mixer.render(256)
    assert mixer.speaking
    mixer.update({}, 0.1)
    mixer.render(256)
    assert not mixer.speaking


# --- Speech synthesis ------------------------------------------------------------------


def wav_bytes(samples: np.ndarray, rate: int, bogus_sizes: bool = True) -> bytes:
    pcm = (samples * 32767).astype("<i2").tobytes()
    size = 0x7FFFFFFF if bogus_sizes else len(pcm)
    header = b"RIFF" + struct.pack("<I", size) + b"WAVE"
    fmt = b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16)
    return header + fmt + b"data" + struct.pack("<I", size) + pcm


def test_parse_wav_ignores_placeholder_sizes() -> None:
    samples = np.linspace(-0.5, 0.5, 100)
    rate, audio = parse_wav(wav_bytes(samples, 22050))
    assert rate == 22050
    np.testing.assert_allclose(audio, samples, atol=1e-4)


def test_parse_wav_rejects_garbage() -> None:
    with pytest.raises(SpeechError):
        parse_wav(b"not audio at all, definitely not a wav file header....")


def test_trim_silence() -> None:
    audio = np.concatenate([np.zeros(1000), np.full(500, 0.5), np.zeros(1000)])
    trimmed = trim_silence(audio, 1000)
    assert 500 <= len(trimmed) <= 540


def test_missing_tts_is_explained(config: Config) -> None:
    cfg = dataclasses.replace(config.training, tts_command="no-such-tts-binary")
    with pytest.raises(SpeechError, match="--no-speech"):
        Speaker(cfg, 48000)


@pytest.mark.skipif(shutil.which("espeak-ng") is None, reason="espeak-ng not installed")
def test_espeak_speech(config: Config) -> None:
    speaker = Speaker(config.training, 48000)
    audio = speaker.say("red cup, left, near")
    assert audio.dtype == np.float32
    assert 0.5 < len(audio) / 48000 < 3.0
    assert np.max(np.abs(audio)) == pytest.approx(config.training.speech_gain, rel=1e-3)
    assert speaker.say("red cup, left, near") is audio  # cached


# --- Stimuli ---------------------------------------------------------------------------


def test_grid_covers_all_combinations() -> None:
    grid = full_grid()
    assert len(grid) == 27 * len(COLOURS)
    assert len(set(grid)) == len(grid)


def test_sample_is_balanced() -> None:
    chosen = sample(54, random.Random(0), colours=("red", "blue"))
    assert len(set(chosen)) == 54
    repeated = sample(60, random.Random(0), colours=("red",))
    assert set(repeated[:27]) == set(full_grid(("red",)))
    assert set(repeated[27:54]) == set(full_grid(("red",)))
