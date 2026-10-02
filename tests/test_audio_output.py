import threading
import types
from pathlib import Path

import numpy as np
import pytest
from scipy.io import wavfile

from naadrik import audio_output
from naadrik.audio_output import AudioOutput, BufferRenderer, play, save_wav
from naadrik.errors import AudioDeviceError


class CallbackStop(Exception):  # noqa: N818 - mirrors sounddevice
    pass


class CallbackAbort(Exception):  # noqa: N818 - mirrors sounddevice
    pass


class PortAudioError(Exception):
    pass


class FakeStream:
    """Drives the callback from a thread, like PortAudio, unless told to misbehave."""

    behaviour = "normal"

    def __init__(self, *, blocksize: int, callback, finished_callback, **_kwargs) -> None:
        self.blocksize = blocksize
        self.callback = callback
        self.finished_callback = finished_callback
        self.latency = 0.01
        self._stop = threading.Event()

    def start(self) -> None:
        if self.behaviour == "hang_on_start":
            threading.Event().wait()
        if self.behaviour == "silent":
            return
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self) -> None:
        status = types.SimpleNamespace(output_underflow=False)
        out = np.zeros((self.blocksize, 2), dtype=np.float32)
        while not self._stop.is_set():
            try:
                self.callback(out, self.blocksize, None, status)
            except (CallbackStop, CallbackAbort):
                break
        self.finished_callback()

    def stop(self) -> None:
        self._stop.set()

    close = abort = stop


@pytest.fixture
def fake_sd(monkeypatch: pytest.MonkeyPatch) -> type[FakeStream]:
    FakeStream.behaviour = "normal"
    module = types.SimpleNamespace(
        OutputStream=FakeStream,
        CallbackStop=CallbackStop,
        CallbackAbort=CallbackAbort,
        PortAudioError=PortAudioError,
    )
    monkeypatch.setattr(audio_output, "_sounddevice", lambda: module)
    monkeypatch.setattr(audio_output, "_START_TIMEOUT_S", 0.2)
    monkeypatch.setattr(audio_output, "_CONTROL_TIMEOUT_S", 0.2)
    monkeypatch.setattr(audio_output, "_abandoned_streams", 0)
    return FakeStream


def test_buffer_renderer_serves_blocks_then_short_block() -> None:
    renderer = BufferRenderer(np.ones((300, 2)))
    assert len(renderer(256)) == 256
    assert len(renderer(256)) == 44
    assert len(renderer(256)) == 0


def test_play_completes(fake_sd: type[FakeStream]) -> None:
    play(np.zeros((2000, 2), dtype=np.float32), 48000, 256)


def test_stream_that_never_calls_back_raises(fake_sd: type[FakeStream]) -> None:
    fake_sd.behaviour = "silent"
    with pytest.raises(AudioDeviceError, match="not consuming audio"):
        play(np.zeros((2000, 2), dtype=np.float32), 48000, 256)


def test_start_that_hangs_raises_and_is_recorded(fake_sd: type[FakeStream]) -> None:
    fake_sd.behaviour = "hang_on_start"
    with pytest.raises(AudioDeviceError, match="did not respond to start"):
        play(np.zeros((2000, 2), dtype=np.float32), 48000, 256)
    assert audio_output.has_abandoned_streams()


def test_renderer_failure_is_reported(fake_sd: type[FakeStream]) -> None:
    def broken(_frames: int) -> np.ndarray:
        raise RuntimeError("boom")

    output = AudioOutput(broken, 48000, 256)
    output.start()
    assert output.finished.wait(1.0)
    output.stop()
    assert isinstance(output.error, RuntimeError)


def test_save_wav_round_trip(tmp_path: Path) -> None:
    buffer = np.stack([np.linspace(-1, 1, 100)] * 2, axis=1)
    path = save_wav(tmp_path / "sub" / "x.wav", buffer, 48000)
    sr, data = wavfile.read(path)
    assert sr == 48000 and data.shape == (100, 2) and data.dtype == np.int16
