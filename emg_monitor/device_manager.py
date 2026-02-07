"""High-level controller orchestrating BLE connection and packet parsing."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Optional

from bleak import BleakClient

from . import data_parser
from .ble import BleController, BleDeviceInfo

logger = logging.getLogger(__name__)


PacketCallback = Callable[[data_parser.EmgSample | data_parser.ImuSample], None]
StatusCallback = Callable[[str], None]


@dataclass
class DeviceManager:
    """Manage BLE lifecycle, including scanning and streaming packets."""

    notification_uuid: str
    on_packet: PacketCallback
    on_status: StatusCallback = lambda msg: None
    controller: BleController = field(default_factory=BleController)

    _client: Optional[BleakClient] = field(init=False, default=None)
    _listen_task: Optional[asyncio.Task[None]] = field(init=False, default=None)

    async def scan(self, timeout: float = 5.0) -> list[BleDeviceInfo]:
        self.on_status("Scanning for devices...")
        devices = await self.controller.scan(timeout=timeout)
        self.on_status(f"Found {len(devices)} device(s)")
        return devices

    async def connect(self, address: str) -> None:
        self.on_status(f"Connecting to {address}...")
        await self.controller.connect(address, disconnect_cb=self._handle_disconnect)
        client = self.controller.client
        if not client or not client.is_connected:
            raise RuntimeError("Failed to connect to device")
        self._client = client
        await client.start_notify(self.notification_uuid, self._handle_notification)
        self.on_status("Connected")

    async def disconnect(self) -> None:
        self.on_status("Disconnecting...")
        if self._client:
            try:
                await self._client.stop_notify(self.notification_uuid)
            except Exception:  # noqa: BLE stop may fail if not started
                logger.debug("stop_notify failed", exc_info=True)
        await self.controller.disconnect()
        self._client = None
        self.on_status("Disconnected")

    def _handle_disconnect(self) -> None:
        self.on_status("Device disconnected")

    def _handle_notification(self, _: int, data: bytearray) -> None:
        try:
            packet = data_parser.parse_packet(bytes(data))
        except data_parser.PacketError:
            logger.debug("Failed to parse packet", exc_info=True)
            return
        self.on_packet(packet)
