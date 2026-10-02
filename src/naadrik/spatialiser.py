"""Streaming binaural spatialiser for a single mono source.

``head_model`` uses the Brown-Duda spherical-head model: a Woodworth interaural time
difference plus a first-order head-shadow filter per ear. It needs no measured HRTF data,
runs in a couple of IIR taps and gives convincing lateralisation on headphones. ``pan`` is
the cheaper fallback: the same ITD with constant-power level panning.

Azimuth: 0 = straight ahead, positive = right, +-180 = behind. Parameters glide across each
block so moving sources never click.
"""

from __future__ import annotations

import math

import numpy as np
from scipy import signal

from naadrik.config import SpatialConfig

SPEED_OF_SOUND_M_S = 343.0
_ALPHA_MIN = 0.1
_THETA_MIN_DEG = 150.0


def wrap_degrees(angle: float) -> float:
    return (angle + 180.0) % 360.0 - 180.0


def lateral_angle(azimuth_deg: float) -> float:
    """Fold rear azimuths onto the front: ITD and ILD depend only on the lateral angle."""
    azimuth = wrap_degrees(azimuth_deg)
    if azimuth > 90.0:
        azimuth = 180.0 - azimuth
    elif azimuth < -90.0:
        azimuth = -180.0 - azimuth
    return math.radians(azimuth)


def interaural_time_difference(azimuth_deg: float, head_radius_m: float) -> float:
    """Woodworth ITD in seconds; positive when the source is on the right (left ear lags)."""
    lateral = lateral_angle(azimuth_deg)
    return head_radius_m / SPEED_OF_SOUND_M_S * (lateral + math.sin(lateral))


def shadow_alpha(angle_from_ear_deg: float) -> float:
    """Brown-Duda high-frequency gain at one ear: 2 facing the source, ~0.1 in the shadow."""
    theta = abs(wrap_degrees(angle_from_ear_deg))
    return (1.0 + _ALPHA_MIN / 2.0) + (1.0 - _ALPHA_MIN / 2.0) * math.cos(
        math.radians(theta / _THETA_MIN_DEG * 180.0)
    )


def ear_alphas(azimuth_deg: float) -> tuple[float, float]:
    """High-frequency gains for (left, right), power-normalised to the frontal position.

    The raw model makes a lateral source up to 6 dB louder than a centred one. Loudness is
    reserved for brightness, so only the interaural ratio is kept.
    """
    left = shadow_alpha(azimuth_deg + 90.0)
    right = shadow_alpha(azimuth_deg - 90.0)
    front = math.sqrt(2.0) * shadow_alpha(90.0)
    scale = front / math.hypot(left, right)
    return left * scale, right * scale


def head_shadow_coefficients(
    alpha: float, head_radius_m: float, sr: int
) -> tuple[np.ndarray, np.ndarray]:
    """Head shadow H(s) = (2w0 + alpha s) / (2w0 + s), discretised by bilinear transform."""
    w0 = SPEED_OF_SOUND_M_S / head_radius_m
    k = 2.0 * sr
    norm = 2.0 * w0 + k
    b = np.array([2.0 * w0 + alpha * k, 2.0 * w0 - alpha * k]) / norm
    a = np.array([1.0, (2.0 * w0 - k) / norm])
    return b, a


class Spatialiser:
    def __init__(self, cfg: SpatialConfig, sample_rate: int) -> None:
        self._cfg = cfg
        self._sr = sample_rate
        max_itd = cfg.head_radius_m / SPEED_OF_SOUND_M_S * (math.pi / 2 + 1.0)
        self._history = np.zeros(math.ceil(max_itd * sample_rate) + 2)
        self._azimuth: float | None = None
        self._delays = np.zeros(2)
        self._gains = np.ones(2)
        self._shadow_state = [np.zeros(1), np.zeros(1)]
        self._rear_b, self._rear_a = signal.butter(1, cfg.rear_lowpass_hz, fs=sample_rate)
        self._rear_state = np.zeros(1)

    def process(self, mono: np.ndarray, azimuth_deg: float) -> np.ndarray:
        """Render one block to stereo, gliding from the previous azimuth to ``azimuth_deg``."""
        n = len(mono)
        if self._azimuth is None:
            self._azimuth = azimuth_deg
            self._delays = self._target_delays(azimuth_deg)
            self._gains = self._target_gains(azimuth_deg)

        source = self._apply_rear_filter(mono.astype(np.float64), azimuth_deg)
        ramp = np.arange(1, n + 1) / n
        target_delays = self._target_delays(azimuth_deg)
        target_gains = self._target_gains(azimuth_deg)

        buffer = np.concatenate([self._history, source])
        base = len(self._history) + np.arange(n)
        out = np.empty((n, 2), dtype=np.float32)
        for ear in range(2):
            delay = self._delays[ear] + (target_delays[ear] - self._delays[ear]) * ramp
            delayed = np.interp(base - delay, np.arange(len(buffer)), buffer)
            if self._cfg.mode == "head_model":
                delayed = self._apply_head_shadow(delayed, azimuth_deg, ear)
            gain = self._gains[ear] + (target_gains[ear] - self._gains[ear]) * ramp
            out[:, ear] = delayed * gain

        self._history = buffer[-len(self._history) :]
        self._azimuth = azimuth_deg
        self._delays = target_delays
        self._gains = target_gains
        return out

    def _target_delays(self, azimuth_deg: float) -> np.ndarray:
        itd = interaural_time_difference(azimuth_deg, self._cfg.head_radius_m) * self._sr
        return np.array([max(itd, 0.0), max(-itd, 0.0)])

    def _target_gains(self, azimuth_deg: float) -> np.ndarray:
        side = math.sin(lateral_angle(azimuth_deg))
        if self._cfg.mode == "pan":
            angle = (side + 1.0) * math.pi / 4.0
            return np.array([math.cos(angle), math.sin(angle)]) * math.sqrt(2.0)
        far_ear_gain = 10.0 ** (-self._cfg.extra_ild_db * abs(side) / 20.0)
        return np.array([far_ear_gain, 1.0]) if side > 0 else np.array([1.0, far_ear_gain])

    def _apply_head_shadow(self, x: np.ndarray, azimuth_deg: float, ear: int) -> np.ndarray:
        alpha = ear_alphas(azimuth_deg)[ear]
        b, a = head_shadow_coefficients(alpha, self._cfg.head_radius_m, self._sr)
        y, self._shadow_state[ear] = signal.lfilter(b, a, x, zi=self._shadow_state[ear])
        return y

    def _apply_rear_filter(self, x: np.ndarray, azimuth_deg: float) -> np.ndarray:
        # Always run the filter so its state is warm when a source swings behind the head.
        dark, self._rear_state = signal.lfilter(self._rear_b, self._rear_a, x, zi=self._rear_state)
        behind = max(0.0, abs(wrap_degrees(azimuth_deg)) - 90.0) / 90.0
        return x if behind == 0.0 else (1.0 - behind) * x + behind * dark
