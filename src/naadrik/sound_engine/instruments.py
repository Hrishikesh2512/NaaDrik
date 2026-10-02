"""Synthesised instruments, one per colour channel.

All timbres are generated from first principles so the project carries no sample licences.
Each function renders a single mono note; pulse gating happens later in the voice.
"""

from __future__ import annotations

import numpy as np
from scipy import signal

from naadrik.config import BowedConfig, FluteConfig, PluckConfig, PresenceConfig

_BUZZ_THRESHOLD = 0.25
_END_FADE_S = 0.01


def pluck_note(
    freq: float, sr: int, duration_s: float, cfg: PluckConfig, rng: np.random.Generator
) -> np.ndarray:
    """Sitar-like plucked string: Karplus-Strong with a bridge buzz and a sympathetic string."""
    n = int(duration_s * sr)
    string = _karplus_strong(
        _pluck_excitation(freq, sr, cfg.brightness, rng), freq, sr, cfg.decay_s, n
    )
    string /= np.max(np.abs(string)) + 1e-12

    # A sitar's curved jawari bridge flattens one side of the string's swing; clipping one
    # polarity reproduces the bright, decaying buzz as the amplitude drops below the contact.
    contact = np.maximum(string - _BUZZ_THRESHOLD, 0.0)
    buzzed = string - cfg.buzz * contact

    sympathetic = _karplus_strong(buzzed * 0.05, 2.0 * freq, sr, cfg.decay_s * 2.0, n)
    sympathetic /= np.max(np.abs(sympathetic)) + 1e-12
    mixed = buzzed + cfg.sympathetic * sympathetic
    if cfg.drive > 0.0:
        mixed = np.tanh(cfg.drive * mixed) / np.tanh(cfg.drive)
    return _finish(mixed, sr)


def bowed_note(
    freq: float, sr: int, duration_s: float, cfg: BowedConfig, rng: np.random.Generator
) -> np.ndarray:
    """Violin-like bowed string: band-limited sawtooth with delayed vibrato and body resonances."""
    n = int(duration_s * sr)
    t = np.arange(n) / sr
    vibrato_ramp = np.clip((t - cfg.vibrato_delay_s) / 0.15, 0.0, 1.0)
    phase = _vibrato_phase(freq, t, sr, cfg.vibrato_hz, cfg.vibrato_cents * vibrato_ramp)

    n_harmonics = max(1, int(min(cfg.cutoff_hz, 0.45 * sr) / freq))
    saw = np.zeros(n)
    for k in range(1, n_harmonics + 1):
        saw += np.sin(k * phase) / k

    body = saw.copy()
    for resonance in cfg.body_resonances_hz:
        if resonance < 0.45 * sr:
            b, a = signal.iirpeak(resonance, Q=4.0, fs=sr)
            body += 0.6 * signal.lfilter(b, a, saw)

    noise = _lowpass(rng.standard_normal(n), 3000.0, sr) * cfg.bow_noise
    attack = np.clip(t / 0.03, 0.0, 1.0)
    return _finish((body / (np.max(np.abs(body)) + 1e-12) + noise) * attack, sr)


def flute_note(
    freq: float, sr: int, duration_s: float, cfg: FluteConfig, rng: np.random.Generator
) -> np.ndarray:
    """Flute: few sine partials, breath noise, an onset chiff and gentle vibrato."""
    n = int(duration_s * sr)
    t = np.arange(n) / sr
    phase = _vibrato_phase(freq, t, sr, cfg.vibrato_hz, np.full(n, cfg.vibrato_cents))
    tone = sum(level * np.sin((k + 1) * phase) for k, level in enumerate(cfg.harmonics))
    tone = tone / (np.max(np.abs(tone)) + 1e-12)

    breath_band = _bandpass(rng.standard_normal(n), freq * 0.8, min(freq * 6.0, 0.45 * sr), sr)
    breath_band /= np.max(np.abs(breath_band)) + 1e-12
    tremolo = 1.0 + cfg.tremolo_depth * np.sin(2 * np.pi * cfg.vibrato_hz * t)
    attack = np.clip(t / 0.04, 0.0, 1.0)
    body = (tone + cfg.breath * breath_band) * tremolo * attack

    chiff = _highpass(rng.standard_normal(n), 1500.0, sr) * np.exp(-t / 0.025)
    chiff /= np.max(np.abs(chiff)) + 1e-12
    return _finish(body + cfg.chiff * chiff, sr)


def presence_note(
    freq: float, sr: int, duration_s: float, cfg: PresenceConfig, rng: np.random.Generator
) -> np.ndarray:
    """Neutral presence hum: a muted triangle at the note's pitch plus soft pitched noise.

    It carries pitch, pulse and position for objects with no colour energy. It is deliberately
    plain (no vibrato, attack transient or breath) so it never reads as one of the colour
    instruments.
    """
    n = int(duration_s * sr)
    t = np.arange(n) / sr
    cutoff = min(cfg.cutoff_ratio * freq, 0.45 * sr)
    hum = np.zeros(n)
    for k in range(1, int(cutoff / freq) + 1, 2):  # odd harmonics, 1/k^2: a triangle
        hum += (-1) ** ((k - 1) // 2) * np.sin(2 * np.pi * k * freq * t) / k**2
    hum = _lowpass(hum, cutoff, sr)
    hum /= np.max(np.abs(hum)) + 1e-12
    noise = _bandpass(rng.standard_normal(n), freq * 0.7, min(freq * 1.5, 0.45 * sr), sr)
    noise /= np.max(np.abs(noise)) + 1e-12
    attack = np.clip(t / 0.02, 0.0, 1.0)
    return _finish(((1.0 - cfg.noise) * hum + cfg.noise * noise) * attack, sr)


def _pluck_excitation(
    freq: float, sr: int, brightness: float, rng: np.random.Generator
) -> np.ndarray:
    length = max(2, int(sr / freq))
    burst = rng.uniform(-1.0, 1.0, length)
    pole = 0.95 - 0.85 * np.clip(brightness, 0.0, 1.0)
    burst = signal.lfilter([1.0 - pole], [1.0, -pole], burst)
    return burst - burst.mean()


def _karplus_strong(
    excitation: np.ndarray, freq: float, sr: int, decay_s: float, n: int
) -> np.ndarray:
    """Karplus-Strong as a single IIR so scipy runs the loop in C.

    The two-point average adds half a sample of delay; the remaining fractional delay is
    folded into the same taps by linear interpolation, keeping every note in tune.
    """
    delay = sr / freq - 0.5
    whole = int(delay)
    frac = delay - whole
    taps = np.convolve([0.5, 0.5], [1.0 - frac, frac])
    loop_gain = 10.0 ** (-3.0 / (decay_s * freq))
    denominator = np.zeros(whole + 3)
    denominator[0] = 1.0
    denominator[whole : whole + 3] -= loop_gain * taps
    drive = np.zeros(n)
    count = min(n, len(excitation))
    drive[:count] = excitation[:count]
    return signal.lfilter([1.0], denominator, drive)


def _vibrato_phase(
    freq: float, t: np.ndarray, sr: int, rate_hz: float, depth_cents: np.ndarray
) -> np.ndarray:
    inst_freq = freq * 2.0 ** (depth_cents / 1200.0 * np.sin(2 * np.pi * rate_hz * t))
    return 2 * np.pi * np.cumsum(inst_freq) / sr


def _lowpass(x: np.ndarray, cutoff: float, sr: int) -> np.ndarray:
    return signal.sosfilt(signal.butter(2, cutoff, "lowpass", fs=sr, output="sos"), x)


def _highpass(x: np.ndarray, cutoff: float, sr: int) -> np.ndarray:
    return signal.sosfilt(signal.butter(2, cutoff, "highpass", fs=sr, output="sos"), x)


def _bandpass(x: np.ndarray, low: float, high: float, sr: int) -> np.ndarray:
    return signal.sosfilt(signal.butter(2, [low, high], "bandpass", fs=sr, output="sos"), x)


def _finish(note: np.ndarray, sr: int) -> np.ndarray:
    fade = int(_END_FADE_S * sr)
    note = note.astype(np.float64, copy=True)
    note[-fade:] *= np.linspace(1.0, 0.0, fade)
    return note
