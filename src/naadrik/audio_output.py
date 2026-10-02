"""Audio playback and file output.

Playback is callback driven: the audio thread pulls blocks from a renderer, so the producer
never has to keep pace by hand. Some host routes (seen with PipeWire's ALSA plugin when the
default sink is a hands-free Bluetooth profile) accept a stream and then never call back, and
hang on stop. Every blocking PortAudio call therefore runs under a watchdog so that failure is
reported instead of freezing the app. sounddevice is imported lazily so tests run without
PortAudio.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
from scipy.io import wavfile

from naadrik.errors import AudioDeviceError

log = logging.getLogger(__name__)

Renderer = Callable[[int], np.ndarray]

_DEVICE_HINT = (
    "Check that headphones are connected and, for Bluetooth, that they use a stereo (A2DP) "
    "profile rather than hands-free. Pick another device with --device; `naadrik devices` "
    "lists them."
)
_START_TIMEOUT_S = 2.0
_CONTROL_TIMEOUT_S = 2.0
_abandoned_streams = 0


def _sounddevice() -> Any:
    try:
        import sounddevice
    except OSError as exc:  # raised when the PortAudio shared library is missing
        raise AudioDeviceError(
            f"PortAudio is not available ({exc}). Install it, e.g. `sudo dnf install portaudio` "
            "or `sudo apt install libportaudio2`."
        ) from exc
    return sounddevice


def has_abandoned_streams() -> bool:
    """True if a hung stream was left behind; PortAudio may then hang at interpreter exit."""
    return _abandoned_streams > 0


def list_devices() -> str:
    return str(_sounddevice().query_devices())


def _run_with_timeout(action: Callable[[], None], timeout_s: float, what: str) -> None:
    errors: list[BaseException] = []

    def target() -> None:
        try:
            action()
        except BaseException as exc:
            errors.append(exc)

    worker = threading.Thread(target=target, name=f"naadrik-audio-{what}", daemon=True)
    worker.start()
    worker.join(timeout_s)
    if worker.is_alive():
        global _abandoned_streams
        _abandoned_streams += 1
        raise AudioDeviceError(f"Audio device did not respond to {what} within {timeout_s:.0f} s.")
    if errors:
        raise errors[0]


class AudioOutput:
    """A running output stream that pulls stereo blocks from ``renderer``.

    The renderer is called on the audio thread with a frame count and must return a float32
    array of shape (frames, 2) quickly; returning fewer frames ends the stream.
    """

    def __init__(
        self,
        renderer: Renderer,
        sample_rate: int,
        block_size: int,
        device: str | int | None = None,
    ) -> None:
        self._renderer = renderer
        self._sample_rate = sample_rate
        self._block_size = block_size
        self._device = device
        self._stream: Any = None
        self._first_callback = threading.Event()
        self.finished = threading.Event()
        self.callbacks = 0
        self.underflows = 0
        self.error: BaseException | None = None

    @property
    def device_name(self) -> str:
        return "default output" if self._device is None else repr(self._device)

    @property
    def latency_s(self) -> float:
        return float(self._stream.latency) if self._stream is not None else 0.0

    def start(self) -> None:
        sd = _sounddevice()
        try:
            self._stream = sd.OutputStream(
                samplerate=self._sample_rate,
                blocksize=self._block_size,
                channels=2,
                dtype="float32",
                device=self._device,
                latency="low",
                callback=self._callback,
                finished_callback=self.finished.set,
            )
            _run_with_timeout(self._stream.start, _CONTROL_TIMEOUT_S, "start")
        except (sd.PortAudioError, ValueError) as exc:
            raise AudioDeviceError(
                f"Could not open audio on {self.device_name}: {exc}. {_DEVICE_HINT}"
            ) from exc
        except AudioDeviceError as exc:
            raise AudioDeviceError(f"{exc} {_DEVICE_HINT}") from exc
        if not self._first_callback.wait(_START_TIMEOUT_S):
            self._abandon()
            raise AudioDeviceError(
                f"Audio stream on {self.device_name} opened but is not consuming audio "
                f"(no callback within {_START_TIMEOUT_S:.0f} s). {_DEVICE_HINT}"
            )
        log.debug("audio started on %s, latency %.1f ms", self.device_name, self.latency_s * 1e3)

    def stop(self) -> None:
        if self._stream is None:
            return
        try:
            _run_with_timeout(self._stream.stop, _CONTROL_TIMEOUT_S, "stop")
            _run_with_timeout(self._stream.close, _CONTROL_TIMEOUT_S, "close")
        except AudioDeviceError as exc:
            log.warning("%s Abandoning the stream.", exc)
        self._stream = None

    def _abandon(self) -> None:
        stream, self._stream = self._stream, None
        if stream is None:
            return
        try:
            _run_with_timeout(stream.abort, _CONTROL_TIMEOUT_S, "abort")
        except AudioDeviceError:
            log.debug("stream abort timed out; leaving it to the OS at exit")

    def _callback(self, outdata: np.ndarray, frames: int, _time: Any, status: Any) -> None:
        self.callbacks += 1
        self._first_callback.set()
        if status.output_underflow:
            self.underflows += 1
        try:
            block = self._renderer(frames)
        except Exception as exc:
            self.error = exc
            outdata.fill(0.0)
            raise _sounddevice().CallbackAbort from exc
        produced = len(block)
        outdata[:produced] = block
        if produced < frames:
            outdata[produced:] = 0.0
            raise _sounddevice().CallbackStop


class BufferRenderer:
    """Serves a pre-rendered buffer block by block; returns a short block at the end."""

    def __init__(self, buffer: np.ndarray) -> None:
        self._buffer = np.ascontiguousarray(buffer, dtype=np.float32)
        self._position = 0

    def __call__(self, frames: int) -> np.ndarray:
        block = self._buffer[self._position : self._position + frames]
        self._position += len(block)
        return block


def play(
    buffer: np.ndarray, sample_rate: int, block_size: int = 256, device: str | int | None = None
) -> None:
    """Play a (frames, 2) buffer and block until it finishes or the device stalls."""
    output = AudioOutput(BufferRenderer(buffer), sample_rate, block_size, device)
    output.start()
    try:
        duration_s = len(buffer) / sample_rate
        if not output.finished.wait(duration_s + 2.0):
            raise AudioDeviceError(f"Playback on {output.device_name} stalled. {_DEVICE_HINT}")
        if output.error is not None:
            raise AudioDeviceError(f"Audio renderer failed: {output.error}") from output.error
    finally:
        output.stop()


def save_wav(path: str | Path, buffer: np.ndarray, sample_rate: int) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = np.clip(buffer, -1.0, 1.0)
    wavfile.write(path, sample_rate, (pcm * 32767).astype(np.int16))
    return path
