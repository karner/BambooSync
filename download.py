"""
Download stored drawings from the Wacom Bamboo Slate.

Downloads the oldest file, saves raw stroke bytes to disk, then deletes it
from the device. Repeat until the device is empty.

Usage:
  python download.py          # download all files
  python download.py --peek   # download but do NOT delete (for inspection)
"""

import asyncio
import binascii
import calendar
import struct
import sys
import time
import tomllib
from pathlib import Path
from bleak import BleakClient, BleakScanner

CONFIG_FILE  = "config.toml"
OUTPUT_DIR   = Path("downloads")

UART_CMD     = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"  # host → device
UART_RESP    = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"  # device → host
OFFLINE_DATA = "ffee0003-bbaa-9988-7766-554433221100"  # stroke data stream


def load_config():
    with open(CONFIG_FILE, "rb") as f:
        return tomllib.load(f)


class Slate:
    def __init__(self, client: BleakClient, host_id: bytes):
        self._client = client
        self._host_id = host_id
        self._queue: asyncio.Queue = asyncio.Queue()
        self._offline_buffer = bytearray()

    async def start(self):
        await self._client.start_notify(UART_RESP, self._on_notify)
        await self._client.start_notify(OFFLINE_DATA, self._on_offline_data)

    def _on_notify(self, sender, data: bytearray):
        opcode = data[0]
        length = data[1] if len(data) > 1 else 0
        payload = bytes(data[2:2 + length])
        print(f"  ← 0x{opcode:02x} {payload.hex()}")
        self._queue.put_nowait((opcode, payload))

    def _on_offline_data(self, sender, data: bytearray):
        self._offline_buffer.extend(data)
        print(f"  [ffee0003] +{len(data):3d} bytes  (total {len(self._offline_buffer)})")

    async def _send(self, opcode: int, args: bytes = b'\x00') -> tuple[int, bytes]:
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
        print("\n[get stroke metadata]")
        reply_op, payload = await self._send(0xcc, b'\x00')
        if reply_op != 0xcf:
            raise RuntimeError(f"Expected 0xcf, got 0x{reply_op:02x}")
        stroke_bytes = struct.unpack_from('<I', payload[0:4])[0]
        ts_str = ''.join(f'{b:02x}' for b in payload[4:])
        t = time.strptime(ts_str, '%y%m%d%H%M%S')
        timestamp = calendar.timegm(t)
        return stroke_bytes, timestamp

    async def download_oldest(self) -> tuple[bytes, int]:
        """
        Trigger download of oldest file. Returns (raw_bytes, crc).
        Stroke data arrives on ffee0003; end signal arrives on uart_resp.
        """
        self._offline_buffer = bytearray()
        print("\n[download oldest file]")

        # Send download command — expect 0xc8 0xbe (transfer started)
        reply_op, payload = await self._send(0xc3, b'\x00')
        if reply_op != 0xc8 or (payload and payload[0] != 0xbe):
            raise RuntimeError(f"Unexpected download start: 0x{reply_op:02x} {payload.hex()}")
        print("  transfer started — collecting data on ffee0003...")

        # Data flows on ffee0003 via _on_offline_data.
        # Wait for end-of-transfer signal: 0xc8 0xed <crc_bytes> on uart_resp.
        reply_op, payload = await asyncio.wait_for(self._queue.get(), timeout=30.0)
        if reply_op != 0xc8 or not payload or payload[0] != 0xed:
            raise RuntimeError(f"Unexpected end signal: 0x{reply_op:02x} {payload.hex()}")

        crc_bytes = bytearray(payload[1:])
        crc_bytes.reverse()
        crc = int(binascii.hexlify(bytes(crc_bytes)), 16) if crc_bytes else 0
        print(f"  transfer complete — {len(self._offline_buffer)} bytes, CRC=0x{crc:08x}")
        return bytes(self._offline_buffer), crc

    async def delete_oldest(self):
        print("\n[delete oldest file]")
        await self._expect_ack(0xca, b'\x00')
        print("  deleted")


async def main():
    peek = "--peek" in sys.argv

    cfg = load_config()
    host_id = bytes.fromhex(cfg["host"]["id"])
    addr = cfg["device"]["address"]

    OUTPUT_DIR.mkdir(exist_ok=True)

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
            print("\nNo drawings on device.")
            return

        downloaded = 0
        while count > 0:
            stroke_bytes, ts = await slate.get_stroke_metadata()
            drawn_at = time.strftime('%Y%m%d_%H%M%S', time.gmtime(ts))
            print(f"\n  Drawing: {drawn_at} UTC, {stroke_bytes} bytes")

            raw, crc = await slate.download_oldest()

            filename = OUTPUT_DIR / f"drawing_{drawn_at}.bin"
            filename.write_bytes(raw)
            print(f"  Saved → {filename}  ({len(raw)} bytes)")

            if not peek:
                await slate.delete_oldest()
            else:
                print("  (--peek mode: file kept on device)")
                break

            downloaded += 1
            count -= 1

        print(f"\nDone — {downloaded} drawing(s) downloaded to {OUTPUT_DIR}/")


if __name__ == "__main__":
    asyncio.run(main())
