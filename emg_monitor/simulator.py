"""Generate mock EMG/IMU data for development without hardware."""

from __future__ import annotations

import math
import os
import random
import time
from typing import Iterator, Tuple

from .data_parser import EmgSample, ImuSample


def emg_waveform_generator(
    frequency_hz: float = 10.0, noise_level: float = 25.0
) -> Iterator[EmgSample]:
    """Yield synthetic 8-channel EMG samples."""
    sequence = 0
    phase_offsets = [random.random() * math.pi for _ in range(8)]
    start = time.monotonic()
    while True:
        t = time.monotonic() - start
        channels = []
        for idx, phase in enumerate(phase_offsets):
            base = math.sin(2 * math.pi * frequency_hz * t + phase) * 150.0
            noise = random.gauss(0, noise_level)
            channels.append(base + noise)
        yield EmgSample(sequence=sequence, channels_uv=channels)
        sequence = (sequence + 1) % 256


def imu_waveform_generator() -> Iterator[ImuSample]:
    """Yield synthetic IMU samples."""
    sequence = 0
    while True:
        gyro = [random.uniform(-1.5, 1.5) for _ in range(3)]
        accel = [random.uniform(-0.5, 0.5) for _ in range(3)]
        remainder = [0] * 6
        yield ImuSample(
            sequence=sequence,
            gyro_rads=gyro,
            accel_mss=accel,
            remainder=remainder,
        )
        sequence = (sequence + 1) % 256
