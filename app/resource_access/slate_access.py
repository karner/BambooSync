"""
Slate BLE resource access.

Component Type: ResourceAccess (Hardware Volatility).
Dumb transport layer over the Wacom Bamboo Slate GATT protocol.
No business logic — connect, download, delete. All protocol opcodes
are sourced from config.toml [protocol] section.
"""

from __future__ import annotations

import asyncio
import calendar
import struct
import time
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager

from typing import Callable

from bleak import BleakClient, BleakScanner, BLEDevice

from app.utilities.logger import get_logger

_log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Interface
# ---------------------------------------------------------------------------

class ISlateAccess(ABC):

    @abstractmethod
    async def find_device(self, address: str, timeout: float) -> BLEDevice | None:
        """Scans BLE and returns the device matching address, or None."""

    @abstractmethod
    async def connect(self, device: BLEDevice) -> "_SlateSession":
        """Returns an async context manager that yields an active _SlateSession."""

    @abstractmethod
    async def file_count(self, session: "_SlateSession") -> int:
        """Returns the number of drawings stored on the device."""

    @abstractmethod
    async def stroke_metadata(self, session: "_SlateSession") -> tuple[int, int]:
        """Returns (stroke_byte_count, unix_timestamp) for the oldest drawing."""

    @abstractmethod
    async def download_oldest(self, session: "_SlateSession") -> bytes:
        """Downloads and returns the raw WILL 2.0 bytes of the oldest drawing."""

    @abstractmethod
    async def delete_oldest(self, session: "_SlateSession") -> None:
        """Deletes the oldest drawing from the device."""

    @abstractmethod
    async def scan_for_devices(
        self,
        timeout: float = 10.0,
        on_device_found: Callable[[BLEDevice], None] | None = None,
    ) -> list[BLEDevice]:
        """Passive scan — calls on_device_found for each new device as it appears, returns full list at completion."""


# ---------------------------------------------------------------------------
# Session (internal context returned by connect)
# ---------------------------------------------------------------------------

class _SlateSession:
    """Active connection to a Slate device."""

    # Characteristic UUIDs
    _UART_CMD     = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
    _UART_RESP    = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
    _OFFLINE_DATA = "ffee0003-bbaa-9988-7766-554433221100"

    def __init__(self, client: BleakClient, host_id: bytes) -> None:
        self.m_client          = client
        self.m_host_id         = host_id
        self.m_queue: asyncio.Queue = asyncio.Queue()
        self.m_offline_buffer  = bytearray()

    async def start(self) -> None:
        await self.m_client.start_notify(self._UART_RESP,    self._on_notify)
        await self.m_client.start_notify(self._OFFLINE_DATA, self._on_offline_data)

    def _on_notify(self, _sender: object, data: bytearray) -> None:
        opcode  = data[0]
        length  = data[1] if len(data) > 1 else 0
        payload = bytes(data[2:2 + length])
        self.m_queue.put_nowait((opcode, payload))

    def _on_offline_data(self, _sender: object, data: bytearray) -> None:
        self.m_offline_buffer.extend(data)

    async def send(self, opcode: int, args: bytes = b"\x00") -> tuple[int, bytes]:
        cmd = bytes([opcode, len(args)]) + args
        await self.m_client.write_gatt_char(self._UART_CMD, cmd, response=False)
        return await asyncio.wait_for(self.m_queue.get(), timeout=5.0)

    async def ack(self, opcode: int, args: bytes = b"\x00") -> None:
        reply_op, payload = await self.send(opcode, args)
        if reply_op != 0xB3:
            raise RuntimeError(f"Expected ACK 0xB3, got 0x{reply_op:02x}")
        if payload and payload[0] != 0x00:
            raise RuntimeError(f"Device error 0x{payload[0]:02x}")


# ---------------------------------------------------------------------------
# Implementation
# ---------------------------------------------------------------------------

class SlateAccess(ISlateAccess):
    """
    BLE GATT access to the Wacom Bamboo Slate.

    Component Type: ResourceAccess (Hardware Volatility).
    Abstracts all BLE transport details. Callers receive raw WILL 2.0 bytes.
    Protocol opcodes are documented in config.toml [protocol].
    """

    def __init__(self, host_id: bytes) -> None:
        if not host_id:
            raise ValueError("host_id must not be empty")
        self.m_host_id = host_id

    async def find_device(self, address: str, timeout: float = 30.0) -> BLEDevice | None:
        return await BleakScanner.find_device_by_address(address, timeout=timeout)

    @asynccontextmanager
    async def connect(self, device: BLEDevice):
        async with BleakClient(device) as client:
            session = _SlateSession(client, self.m_host_id)
            await session.start()

            reply_op, _ = await session.send(0xE6, self.m_host_id)
            if reply_op not in (0x50, 0xB3):
                if reply_op == 0x51:
                    raise RuntimeError("Auth failed — re-run register.py")
                raise RuntimeError(f"Unexpected connect reply: 0x{reply_op:02x}")

            await session.ack(0xEC, bytes([0x06, 0x00, 0x00, 0x00, 0x00, 0x00]))
            await session.ack(0xB1, bytes([0x01]))

            yield session

    async def file_count(self, session: _SlateSession) -> int:
        reply_op, payload = await session.send(0xC1, b"\x00")
        if reply_op != 0xC2:
            raise RuntimeError(f"Expected 0xC2, got 0x{reply_op:02x}")
        return struct.unpack_from("<H", payload)[0]

    async def stroke_metadata(self, session: _SlateSession) -> tuple[int, int]:
        reply_op, payload = await session.send(0xCC, b"\x00")
        if reply_op != 0xCF:
            raise RuntimeError(f"Expected 0xCF, got 0x{reply_op:02x}")
        stroke_bytes = struct.unpack_from("<I", payload[0:4])[0]
        ts_str = "".join(f"{b:02x}" for b in payload[4:])
        t = time.strptime(ts_str, "%y%m%d%H%M%S")
        return stroke_bytes, calendar.timegm(t)

    async def download_oldest(self, session: _SlateSession) -> bytes:
        session.m_offline_buffer = bytearray()
        reply_op, payload = await session.send(0xC3, b"\x00")
        if reply_op != 0xC8 or (payload and payload[0] != 0xBE):
            raise RuntimeError(f"Download start failed: 0x{reply_op:02x} {payload.hex()}")
        reply_op, payload = await asyncio.wait_for(session.m_queue.get(), timeout=30.0)
        if reply_op != 0xC8 or not payload or payload[0] != 0xED:
            raise RuntimeError(f"Unexpected end signal: 0x{reply_op:02x} {payload.hex()}")
        return bytes(session.m_offline_buffer)

    async def delete_oldest(self, session: _SlateSession) -> None:
        await session.ack(0xCA, b"\x00")

    async def scan_for_devices(
        self,
        timeout: float = 10.0,
        on_device_found: Callable[[BLEDevice], None] | None = None,
    ) -> list[BLEDevice]:
        seen: dict[str, BLEDevice] = {}

        def _callback(device: BLEDevice, _adv) -> None:
            if device.address not in seen:
                seen[device.address] = device
                if on_device_found is not None:
                    on_device_found(device)

        scanner = BleakScanner(detection_callback=_callback)
        await scanner.start()
        await asyncio.sleep(timeout)
        await scanner.stop()
        return list(seen.values())
