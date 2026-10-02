import numpy as np
import pytest

from naadrik.config import Config
from naadrik.sound_engine.instruments import bowed_note, flute_note, pluck_note, presence_note
from naadrik.sound_engine.notes import INSTRUMENTS, NoteBank

SR = 48000


def estimate_f0(x: np.ndarray, sr: int, fmin: float = 80.0, fmax: float = 2000.0) -> float:
    """Autocorrelation pitch with parabolic peak refinement."""
    x = x - x.mean()
    corr = np.fft.irfft(np.abs(np.fft.rfft(x, 2 * len(x))) ** 2)[: len(x)]
    lo, hi = int(sr / fmax), int(sr / fmin)
    lag = lo + int(np.argmax(corr[lo:hi]))
    a, b, c = corr[lag - 1], corr[lag], corr[lag + 1]
    lag += 0.5 * (a - c) / (a - 2 * b + c)
    return sr / lag


def cents(f: float, ref: float) -> float:
    return 1200 * np.log2(f / ref)


@pytest.fixture(scope="module")
def bank(config: Config) -> NoteBank:
    return NoteBank(config)


@pytest.mark.parametrize("freq", [196.0, 440.0, 1046.5])
@pytest.mark.parametrize("instrument", ["pluck", "bowed", "flute", "presence"])
def test_notes_are_in_tune(config: Config, instrument: str, freq: float) -> None:
    render = {
        "pluck": pluck_note,
        "bowed": bowed_note,
        "flute": flute_note,
        "presence": presence_note,
    }[instrument]
    cfg = getattr(config.instruments, instrument)
    note = render(freq, SR, 0.5, cfg, np.random.default_rng(0))
    segment = note[int(0.05 * SR) : int(0.25 * SR)]
    assert abs(cents(estimate_f0(segment, SR), freq)) < 20


def test_pluck_decays(config: Config) -> None:
    note = pluck_note(220.0, SR, 1.0, config.instruments.pluck, np.random.default_rng(0))
    early = np.sqrt(np.mean(note[: SR // 10] ** 2))
    late = np.sqrt(np.mean(note[-SR // 5 :] ** 2))
    assert late < early / 3


def test_bowed_is_harmonically_richer_than_flute(config: Config) -> None:
    def spectral_centroid(x: np.ndarray) -> float:
        power = np.abs(np.fft.rfft(x)) ** 2
        freqs = np.fft.rfftfreq(len(x), 1 / SR)
        return float((freqs * power).sum() / power.sum())

    rng = np.random.default_rng(0)
    bowed = bowed_note(330.0, SR, 0.5, config.instruments.bowed, rng)[SR // 10 :]
    flute = flute_note(330.0, SR, 0.5, config.instruments.flute, rng)[SR // 10 :]
    assert spectral_centroid(bowed) > 1.5 * spectral_centroid(flute)


def test_bank_shape_and_bounds(bank: NoteBank, config: Config) -> None:
    assert bank.n_degrees == 13
    assert bank.note_length == int(config.instruments.note_duration_s * config.audio.sample_rate)
    for instrument in INSTRUMENTS:
        for degree in range(bank.n_degrees):
            note = bank.note(instrument, degree)
            assert np.all(np.isfinite(note))
            assert np.max(np.abs(note)) <= 1.0 + 1e-6


def test_bank_notes_ascend(bank: NoteBank) -> None:
    pitches = [estimate_f0(bank.note("flute", d)[4800:14400], SR) for d in range(bank.n_degrees)]
    assert np.all(np.diff(pitches) > 0)


def test_mix_is_presence_plus_weighted_instruments(bank: NoteBank, config: Config) -> None:
    presence = config.instruments.presence.level * bank.presence(3)
    np.testing.assert_allclose(bank.mix(3, (0.0, 0.0, 0.0)), presence, atol=1e-6)
    np.testing.assert_allclose(
        bank.mix(3, (1.0, 0.0, 0.0)), bank.note("pluck", 3) + presence, atol=1e-6
    )
    assert bank.mix(3, (1.0, 0.0, 0.0)) is bank.mix(3, (1.0, 0.0, 0.0))


def test_presence_is_muted_compared_with_colour_instruments(config: Config) -> None:
    def centroid(x: np.ndarray) -> float:
        power = np.abs(np.fft.rfft(x)) ** 2
        return float((np.fft.rfftfreq(len(x), 1 / SR) * power).sum() / power.sum())

    rng = np.random.default_rng(0)
    inst = config.instruments
    presence = centroid(presence_note(330.0, SR, 0.5, inst.presence, rng)[SR // 10 :])
    for render, cfg in ((pluck_note, inst.pluck), (bowed_note, inst.bowed)):
        assert presence < centroid(render(330.0, SR, 0.5, cfg, rng)[SR // 10 :])
    assert presence < 2 * 330.0
