"""Audio playback and file output. sounddevice is imported lazily so tests run without PortAudio."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from scipy.io import wavfile

from naadrik.errors import AudioDeviceError

_DEVICE_HINT = "Check that headphones are connected, or pick another device with `naadrik devices`."


def _sounddevice():  # type: ignore[no-untyped-def]
    try:
        import sounddevice
    except OSError as exc:  # raised when the PortAudio shared library is missing
        raise AudioDeviceError(
            f"PortAudio is not available ({exc}). Install it, e.g. `sudo dnf install portaudio` "
            "or `sudo apt install libportaudio2`."
        ) from exc
    return sounddevice


def list_devices() -> str:
    return str(_sounddevice().query_devices())


def play(buffer: np.ndarray, sample_rate: int, device: str | int | None = None) -> None:
    """Play a (frames, 2) buffer and block until it finishes."""
    sd = _sounddevice()
    try:
        sd.play(buffer, samplerate=sample_rate, device=device, blocking=True)
    except (sd.PortAudioError, ValueError) as exc:
        name = "default output" if device is None else repr(device)
        raise AudioDeviceError(f"Could not play audio on {name}: {exc}. {_DEVICE_HINT}") from exc


def save_wav(path: str | Path, buffer: np.ndarray, sample_rate: int) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = np.clip(buffer, -1.0, 1.0)
    wavfile.write(path, sample_rate, (pcm * 32767).astype(np.int16))
    return path
