"""Data buffers for aggregating EMG samples for plotting."""

from __future__ import annotations

import numpy as np


class EmgRingBuffer:
    """Maintain a fixed-size rolling buffer of EMG channels."""

    def __init__(self, channels: int, capacity: int) -> None:
        self.channels = channels
        self.capacity = capacity
        self._data = np.zeros((channels, capacity), dtype=np.float32)
        self._index = 0
        self._filled = False

    def append(self, values: list[float]) -> None:
        if len(values) != self.channels:
            raise ValueError(f"Expected {self.channels} values, got {len(values)}")
        self._data[:, self._index] = values
        self._index = (self._index + 1) % self.capacity
        if self._index == 0:
            self._filled = True

    def snapshot(self) -> np.ndarray:
        """Return data ordered from oldest to newest."""
        if not self._filled:
            return self._data[:, : self._index]
        idx = self._index
        return np.concatenate(
            (self._data[:, idx:], self._data[:, :idx]), axis=1
        )

    def clear(self) -> None:
        self._data.fill(0)
        self._index = 0
        self._filled = False
