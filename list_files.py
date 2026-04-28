"""
List stored drawings on the Wacom Bamboo Slate.

The device only exposes the oldest file at a time, so this shows:
  - total file count
  - timestamp + stroke count of the oldest drawing

Usage (short press to power on — no pairing mode needed after registration):
  python list_files.py
"""

import asyncio
import calendar
import struct
import sys
import time
import tomllib
from bleak import BleakClient, BleakScanner

CONFIG_FILE = "config.toml"

UART_CMD  = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"  # host → device
UART_RESP = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"  # device → host


def load_config():
    with open(CONFIG_FILE, "rb") as f:
        return tomllib.load(f)


# ---------------------------------------------------------------------------
# Low-level request/response over Nordic UART
# ---------------------------------------------------------------------------

class Slate:
    def __init__(self, client: BleakClient, host_id: bytes):
        self._client = client
        self._host_id = host_id
        self._queue: asyncio.Queue = asyncio.Queue()

    async def start(self):
        await self._client.start_notify(UART_RESP, self._on_notify)

    def _on_notify(self, sender, data: bytearray):
        opcode = data[0]
        length = data[1] if len(data) > 1 else 0
        payload = bytes(data[2:2 + length])
        print(f"  ← 0x{opcode:02x} {payload.hex()}")
        self._queue.put_nowait((opcode, payload))

    async def _send(self, opcode: int, args: bytes = b'\x00') -> tuple[int, bytes]:
        """Send one NordicData command and return (reply_opcode, reply_payload)."""
        cmd = bytes([opcode, len(args)]) + args
        print(f"  → 0x{opcode:02x} {args.hex()}")
        await self._client.write_gatt_char(UART_CMD, cmd, response=False)
        return await asyncio.wait_for(self._queue.get(), timeout=5.0)

    async def _expect_ack(self, opcode: int, args: bytes = b'\x00'):
        reply_op, payload = await self._send(opcode, args)
        if reply_op != 0xb3:
            raise RuntimeError(f"Expected ACK 0xb3, got 0x{reply_op:02x}")
        if payload and payload[0] != 0x00:
            raise RuntimeError(f"Device error: 0x{payload[0]:02x}")

    # -----------------------------------------------------------------------
    # Protocol commands
    # -----------------------------------------------------------------------

    async def connect(self):
        print("\n[connect]")
        reply_op, payload = await self._send(0xe6, self._host_id)
        if reply_op in (0x50, 0xb3):
            print("  connected ok")
        elif reply_op == 0x51:
            reason = payload[6] if len(payload) > 6 else 0xff
            raise RuntimeError(f"Auth failed (reason 0x{reason:02x}) — re-run register.py?")
        else:
            raise RuntimeError(f"Unexpected connect reply: 0x{reply_op:02x}")

    async def select_transfer_gatt(self):
        """Route offline data to ffee0003."""
        print("\n[set file transfer reporting type]")
        await self._expect_ack(0xec, bytes([0x06, 0x00, 0x00, 0x00, 0x00, 0x00]))

    async def set_paper_mode(self):
        print("\n[set mode → PAPER]")
        await self._expect_ack(0xb1, bytes([0x01]))

    async def file_count(self) -> int:
        print("\n[available file count]")
        reply_op, payload = await self._send(0xc1, b'\x00')
        if reply_op != 0xc2:
            raise RuntimeError(f"Expected 0xc2, got 0x{reply_op:02x}")
        count = struct.unpack_from('<H', payload)[0]
        print(f"  {count} file(s) on device")
        return count

    async def get_stroke_metadata(self) -> tuple[int, int]:
        """Returns (stroke_byte_count, unix_timestamp) for the oldest file."""
        print("\n[get stroke metadata]")
        reply_op, payload = await self._send(0xcc, b'\x00')
        if reply_op != 0xcf:
            raise RuntimeError(f"Expected 0xcf, got 0x{reply_op:02x}")
        stroke_count = struct.unpack_from('<I', payload[0:4])[0]
        ts_str = ''.join(f'{b:02x}' for b in payload[4:])
        t = time.strptime(ts_str, '%y%m%d%H%M%S')
        timestamp = calendar.timegm(t)
        return stroke_count, timestamp


# ---------------------------------------------------------------------------

async def main():
    cfg = load_config()
    host_id = bytes.fromhex(cfg["host"]["id"])
    addr = cfg["device"]["address"]

    print(f"Scanning for {addr} (30s) — short-press the Slate to power on...")
    device = await BleakScanner.find_device_by_address(addr, timeout=30.0)
    if not device:
        print("Device not found.")
        sys.exit(1)

    print(f"Found: {device.name} — connecting...")
    async with BleakClient(device) as client:
        slate = Slate(client, host_id)
        await slate.start()

        await slate.connect()
        await slate.select_transfer_gatt()
        await slate.set_paper_mode()

        count = await slate.file_count()
        if count == 0:
            print("\nNo drawings stored on device.")
            return

        stroke_bytes, ts = await slate.get_stroke_metadata()
        drawn_at = time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime(ts))

        print(f"\n{'─' * 40}")
        print(f"Files on device : {count}")
        print(f"Oldest drawing  : {drawn_at}")
        print(f"Stroke data size: {stroke_bytes} bytes")
        if count > 1:
            print(f"(+{count - 1} more — download oldest first to see the rest)")


if __name__ == "__main__":
    asyncio.run(main())
