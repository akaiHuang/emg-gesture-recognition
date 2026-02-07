"""Drop-in replacement for DeviceManager that emits simulated data."""

from __future__ import annotations

import asyncio
from typing import Callable, Optional

from . import config
from .data_parser import EmgSample, ImuSample
from .simulator import emg_waveform_generator, imu_waveform_generator


class SimulatedDeviceManager:
    """Mimic the DeviceManager API using synthetic signals."""

    def __init__(
        self,
        on_packet: Callable[[EmgSample | ImuSample], None],
        on_status: Callable[[str], None] = lambda msg: None,
    ) -> None:
        self._on_packet = on_packet
        self._on_status = on_status
        self._running = False
        self._task: Optional[asyncio.Task[None]] = None

    async def scan(self, timeout: float = 0.0):
        self._on_status("Simulation ready")
        return []

    async def connect(self, address: str = "SIM") -> None:
        if self._running:
            return
        self._on_status("Starting simulator...")
        self._running = True
        loop = asyncio.get_running_loop()
        self._task = loop.create_task(self._run())

    async def disconnect(self) -> None:
        self._on_status("Stopping simulator...")
        self._running = False
        if self._task:
            await self._task
            self._task = None
        self._on_status("Simulation stopped")

    async def _run(self) -> None:
        emg_gen = emg_waveform_generator()
        imu_gen = imu_waveform_generator()
        period = 1.0 / config.SAMPLE_RATE_HZ
        imu_counter = 0
        while self._running:
            sample = next(emg_gen)
            self._on_packet(sample)
            imu_counter = (imu_counter + 1) % 20
            if imu_counter == 0:
                self._on_packet(next(imu_gen))
            await asyncio.sleep(period)
