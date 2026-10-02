"""Offline text-to-speech through eSpeak NG, run as a subprocess (no network, no linking)."""

from __future__ import annotations

import shutil
import struct
import subprocess
from functools import lru_cache

import numpy as np
from scipy import signal

from naadrik.config import TrainingConfig
from naadrik.errors import SpeechError

_SILENCE_THRESHOLD = 0.01
_EDGE_PAD_S = 0.02
_TIMEOUT_S = 5.0


def parse_wav(data: bytes) -> tuple[int, np.ndarray]:
    """Decode 16-bit mono PCM WAV.

    Written to a pipe, eSpeak cannot seek back to fill in chunk sizes, so the header's
    lengths are placeholders; the audio is simply everything after the ``data`` tag.
    """
    if len(data) < 44 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise SpeechError("Text-to-speech returned data that is not a WAV file.")
    channels, sample_rate = struct.unpack_from("<HI", data, 22)
    bits = struct.unpack_from("<H", data, 34)[0]
    start = data.find(b"data", 12)
    if start < 0 or bits != 16 or channels != 1:
        raise SpeechError("Text-to-speech returned an unsupported WAV format.")
    payload = data[start + 8 :]
    samples = np.frombuffer(payload[: len(payload) // 2 * 2], dtype="<i2")
    return sample_rate, samples.astype(np.float32) / 32768.0


def trim_silence(audio: np.ndarray, sample_rate: int) -> np.ndarray:
    loud = np.flatnonzero(np.abs(audio) > _SILENCE_THRESHOLD)
    if len(loud) == 0:
        return audio[:0]
    pad = int(_EDGE_PAD_S * sample_rate)
    return audio[max(0, loud[0] - pad) : loud[-1] + pad]


class Speaker:
    def __init__(self, cfg: TrainingConfig, sample_rate: int) -> None:
        executable = shutil.which(cfg.tts_command)
        if executable is None:
            raise SpeechError(
                f"Offline text-to-speech '{cfg.tts_command}' was not found. Install it "
                "(e.g. `sudo dnf install espeak-ng` or `sudo apt install espeak-ng`), "
                "or run training with --no-speech."
            )
        self._command = [executable, "-v", cfg.voice, "-s", str(cfg.words_per_minute), "--stdout"]
        self._sample_rate = sample_rate
        self._gain = cfg.speech_gain
        self.say = lru_cache(maxsize=256)(self._synthesise)

    def _synthesise(self, text: str) -> np.ndarray:
        """Mono float32 speech at the engine sample rate, silence trimmed."""
        try:
            result = subprocess.run(
                [*self._command, text], capture_output=True, timeout=_TIMEOUT_S, check=True
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise SpeechError(f"Text-to-speech failed for {text!r}: {exc}") from exc
        source_rate, audio = parse_wav(result.stdout)
        audio = trim_silence(audio, source_rate)
        if source_rate != self._sample_rate:
            divisor = np.gcd(source_rate, self._sample_rate)
            audio = signal.resample_poly(
                audio, self._sample_rate // divisor, source_rate // divisor
            )
        peak = float(np.max(np.abs(audio))) if len(audio) else 0.0
        if peak > 0:
            audio = audio / peak * self._gain
        return audio.astype(np.float32)
