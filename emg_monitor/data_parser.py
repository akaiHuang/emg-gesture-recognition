"""Utilities for decoding WL-EMG binary packets into structured data."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence, Tuple, Union


HEADER = bytes([0xD2, 0xD2, 0xD2])
PAYLOAD_LENGTH = 29


@dataclass
class EmgSample:
    """Represents one timestamped sample across all EMG channels."""

    sequence: int
    channels_uv: List[float]


@dataclass
class ImuSample:
    """Represents one IMU sample for gyroscope and accelerometer axes."""

    sequence: int
    gyro_rads: List[float]
    accel_mss: List[float]
    remainder: List[int]


class PacketError(Exception):
    """Signals that an incoming packet cannot be decoded."""


def _combine_signed(bytes_seq: Sequence[int], bits: int) -> int:
    """Combine big-endian bytes into a signed integer."""
    value = 0
    for byte in bytes_seq:
        value = (value << 8) | byte
    sign_bit = 1 << (bits - 1)
    return value - (1 << bits) if value & sign_bit else value


def parse_packet(raw: bytes) -> Union[EmgSample, ImuSample]:
    """Parse a 29-byte packet into an EMG or IMU sample.

    Raises PacketError when the packet format is invalid."""
    if len(raw) != PAYLOAD_LENGTH:
        raise PacketError(f"Expected {PAYLOAD_LENGTH} bytes, got {len(raw)}")
    if not raw.startswith(HEADER):
        raise PacketError(f"Packet missing header {HEADER!r}")

    packet_type = raw[3]
    sequence = raw[4]
    payload = raw[5:]

    if packet_type == 0xAA:
        channels: List[float] = []
        for offset in range(0, len(payload), 3):
            chunk = payload[offset : offset + 3]
            if len(chunk) < 3:
                break
            value = float(_combine_signed(chunk, 24))
            channels.append(value)  # Already expressed in microvolts per spec
        return EmgSample(sequence=sequence, channels_uv=channels)

    if packet_type == 0xBB:
        decoded: List[int] = []
        for offset in range(0, len(payload), 2):
            chunk = payload[offset : offset + 2]
            if len(chunk) < 2:
                break
            decoded.append(_combine_signed(chunk, 16))
        gyro_rads = [val * 0.0012 for val in decoded[:3]]
        accel_mss = [val * 0.0005978 for val in decoded[3:6]]
        remainder = decoded[6:]
        return ImuSample(
            sequence=sequence,
            gyro_rads=gyro_rads,
            accel_mss=accel_mss,
            remainder=remainder,
        )

    raise PacketError(f"Unknown packet type 0x{packet_type:02X}")
