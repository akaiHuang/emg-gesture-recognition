"""Bluetooth Low Energy helpers built on top of bleak."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Callable, Coroutine, List, Optional, TypeVar

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice


@dataclass
class BleDeviceInfo:
    """Snapshot of a BLE device discovered during a scan."""

    name: str
    address: str
    rssi: Optional[int]


class BleController:
    """Wraps BLE scanning and connection lifecycle."""

    def __init__(self) -> None:
        self._client: Optional[BleakClient] = None
        self._disconnect_cb: Optional[Callable[[], None]] = None

    async def scan(self, timeout: float = 5.0) -> List[BleDeviceInfo]:
        """Scan for BLE devices."""
        scanner = BleakScanner()
        devices_dict = await scanner.discover(timeout=timeout, return_adv=True)
        
        result = []
        for device, adv_data in devices_dict.values():
            result.append(
                BleDeviceInfo(
                    name=device.name or "(unknown)",
                    address=device.address,
                    rssi=adv_data.rssi,
                )
            )
        return result

    async def connect(
        self,
        address: str,
        disconnect_cb: Optional[Callable[[], None]] = None,
    ) -> None:
        """Connect to a device by address."""
        await self.disconnect()
        self._client = BleakClient(address)
        self._disconnect_cb = disconnect_cb
        await self._client.connect()
        if self._disconnect_cb:
            self._client.set_disconnected_callback(lambda _: self._disconnect_cb())

    async def disconnect(self) -> None:
        """Disconnect from the current device if connected."""
        if self._client and self._client.is_connected:
            await self._client.disconnect()
        self._client = None

    def client(self) -> Optional[BleakClient]:
        return self._client


T = TypeVar("T")


def run_coroutine(coro: Coroutine[None, None, T]) -> T:
    """Run an asyncio coroutine from sync code."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)
