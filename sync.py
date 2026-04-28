"""
Wacom Bamboo Slate — full sync pipeline.

Connects to the device, downloads all stored drawings, renders each to a
PNG, then deletes the drawing from the device. No intermediate files kept.

Usage:
  python sync.py               # sync to ./drawings/
  python sync.py ~/Desktop     # sync to a custom output directory
"""

import asyncio
import binascii
import calendar
import struct
import sys
import time
import tomllib
from collections import namedtuple
from pathlib import Path

from bleak import BleakClient, BleakScanner
from PIL import Image, ImageDraw

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

CONFIG_FILE  = "config.toml"
DEFAULT_OUT  = Path("drawings")

UART_CMD     = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
UART_RESP    = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
OFFLINE_DATA = "ffee0003-bbaa-9988-7766-554433221100"
FILE_MAGIC   = bytes([0x62, 0x38, 0x62, 0x74])


def load_config():
    with open(CONFIG_FILE, "rb") as f:
        return tomllib.load(f)


# ---------------------------------------------------------------------------
# BLE / Slate protocol
# ---------------------------------------------------------------------------

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
        self._queue.put_nowait((opcode, payload))

    def _on_offline_data(self, sender, data: bytearray):
        self._offline_buffer.extend(data)

    async def _send(self, opcode: int, args: bytes = b'\x00') -> tuple[int, bytes]:
        cmd = bytes([opcode, len(args)]) + args
        await self._client.write_gatt_char(UART_CMD, cmd, response=False)
        return await asyncio.wait_for(self._queue.get(), timeout=5.0)

    async def _ack(self, opcode: int, args: bytes = b'\x00'):
        reply_op, payload = await self._send(opcode, args)
        if reply_op != 0xb3:
            raise RuntimeError(f"Expected ACK 0xb3, got 0x{reply_op:02x}")
        if payload and payload[0] != 0x00:
            raise RuntimeError(f"Device error 0x{payload[0]:02x}")

    async def connect(self):
        reply_op, payload = await self._send(0xe6, self._host_id)
        if reply_op not in (0x50, 0xb3):
            if reply_op == 0x51:
                raise RuntimeError("Auth failed — re-run register.py")
            raise RuntimeError(f"Unexpected connect reply: 0x{reply_op:02x}")

    async def setup(self):
        await self._ack(0xec, bytes([0x06, 0x00, 0x00, 0x00, 0x00, 0x00]))  # route data to ffee0003
        await self._ack(0xb1, bytes([0x01]))                                  # paper mode

    async def file_count(self) -> int:
        reply_op, payload = await self._send(0xc1, b'\x00')
        if reply_op != 0xc2:
            raise RuntimeError(f"Expected 0xc2, got 0x{reply_op:02x}")
        return struct.unpack_from('<H', payload)[0]

    async def stroke_metadata(self) -> tuple[int, int]:
        reply_op, payload = await self._send(0xcc, b'\x00')
        if reply_op != 0xcf:
            raise RuntimeError(f"Expected 0xcf, got 0x{reply_op:02x}")
        stroke_bytes = struct.unpack_from('<I', payload[0:4])[0]
        ts_str = ''.join(f'{b:02x}' for b in payload[4:])
        t = time.strptime(ts_str, '%y%m%d%H%M%S')
        return stroke_bytes, calendar.timegm(t)

    async def download_oldest(self) -> bytes:
        self._offline_buffer = bytearray()
        reply_op, payload = await self._send(0xc3, b'\x00')
        if reply_op != 0xc8 or (payload and payload[0] != 0xbe):
            raise RuntimeError(f"Download start failed: 0x{reply_op:02x} {payload.hex()}")
        # Wait for end-of-transfer: 0xc8 0xed <crc> on uart_resp
        reply_op, payload = await asyncio.wait_for(self._queue.get(), timeout=30.0)
        if reply_op != 0xc8 or not payload or payload[0] != 0xed:
            raise RuntimeError(f"Unexpected end signal: 0x{reply_op:02x} {payload.hex()}")
        return bytes(self._offline_buffer)

    async def delete_oldest(self):
        await self._ack(0xca, b'\x00')


# ---------------------------------------------------------------------------
# WILL 2.0 stroke parser (Spark/Slate format)
# ---------------------------------------------------------------------------

Point = namedtuple('Point', ['x', 'y', 'p'])


def _nbits(b: int) -> int:
    return bin(b).count('1')


def _identify(data: list) -> str:
    h, nb = data[0], _nbits(data[0])
    payload = data[1:1 + nb]
    if data[0:4] == [0x62, 0x38, 0x62, 0x74]:
        return 'FILE_HEADER'
    if data[0:7] == [0xfc, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff]:
        return 'STROKE_END'
    if payload == [0xff] * nb and nb == 8:
        return 'EOF'
    if h & 0x3 == 0:
        return 'DELTA'
    if not payload:
        return 'UNKNOWN'
    if payload[0:3] == [0xff, 0xee, 0xee]:
        return 'STROKE_HEADER'
    if payload[0:2] == [0xff, 0xff]:
        return 'POINT'
    return 'UNKNOWN'


def _extract(mask: int, data: list) -> tuple[int | None, int | None, int]:
    if mask == 0:
        return None, None, 0
    if mask == 2:
        return None, int.from_bytes(bytes([data[0]]), signed=True), 1
    if mask == 3:
        return data[0] + (data[1] << 8), None, 2
    raise ValueError(f'Bad mask {mask}')


def _parse_delta(header: int, data: list) -> tuple:
    off = 1
    x, dx, s = _extract((header >> 2) & 3, data[off:]); off += s
    y, dy, s = _extract((header >> 4) & 3, data[off:]); off += s
    p, dp, s = _extract((header >> 6) & 3, data[off:]); off += s
    return x, dx, y, dy, p, dp, off


def parse_strokes(raw: bytes) -> list[list[Point]]:
    if raw[:4] != FILE_MAGIC:
        raise ValueError(f'Unknown magic: {raw[:4].hex()}')

    data = list(raw[4:])
    strokes, points = [], []
    lp = Point(0, 0, 0)   # last absolute point
    ld = Point(0, 0, 0)   # cumulative delta

    while data:
        t = _identify(data)

        if t == 'STROKE_HEADER':
            if points:
                strokes.append(points)
            points = []
            ld = Point(0, 0, 0)
            data = data[1 + _nbits(data[0]):]

        elif t == 'STROKE_END':
            if points:
                strokes.append(points)
            points = []
            data = data[1 + _nbits(data[0]):]

        elif t == 'EOF':
            if points:
                strokes.append(points)
            data = data[1 + _nbits(data[0]):]
            break

        elif t in ('DELTA', 'POINT'):
            if t == 'POINT':
                h = data[0] & ~0x3
                x, dx, y, dy, p, dp, inner = _parse_delta(h, [h] + data[3:])
                size = 1 + 2 + inner - 1
            else:
                x, dx, y, dy, p, dp, size = _parse_delta(data[0], data)

            # Unpack accumulated delta and last absolute position
            cdx, cdy, cdp = ld.x, ld.y, ld.p
            ax, ay, ap = lp.x, lp.y, lp.p

            # Per-axis: accumulate delta OR adopt new absolute (resets delta)
            if dx is not None:
                cdx += dx
            elif x is not None:
                ax, cdx = x, 0

            if dy is not None:
                cdy += dy
            elif y is not None:
                ay, cdy = y, 0

            if dp is not None:
                cdp += dp
            elif p is not None:
                ap, cdp = p, 0

            ld = Point(cdx, cdy, cdp)
            lp = Point(ax + cdx, ay + cdy, ap + cdp)
            points.append(lp)
            data = data[size:]

        else:
            data = data[1 + _nbits(data[0]):]

    return strokes


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------

def render(strokes: list[list[Point]], out_path: Path, width_px: int = 2480):
    all_pts = [p for s in strokes for p in s]
    if not all_pts:
        print("  No points to render — skipping.")
        return

    xs = [p.x for p in all_pts]
    ys = [p.y for p in all_pts]
    p_max = max(p.p for p in all_pts) or 1

    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)
    span_x = x_max - x_min or 1
    span_y = y_max - y_min or 1

    height_px = int(width_px * span_y / span_x)
    margin = 0.05

    def tx(x): return int((x - x_min) / span_x * width_px * (1 - 2 * margin) + width_px * margin)
    def ty(y): return int((y - y_min) / span_y * height_px * (1 - 2 * margin) + height_px * margin)

    img = Image.new('RGB', (width_px, height_px), 'white')
    draw = ImageDraw.Draw(img)

    for stroke in strokes:
        if len(stroke) < 2:
            continue
        for a, b in zip(stroke, stroke[1:]):
            pressure = (a.p + b.p) / 2
            w = max(1, int(pressure / p_max * 6))
            draw.line([(tx(a.x), ty(a.y)), (tx(b.x), ty(b.y))], fill='black', width=w)

    img = img.rotate(-90, expand=True)
    img.save(out_path)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main(out_dir: Path):
    cfg = load_config()
    host_id = bytes.fromhex(cfg["host"]["id"])
    addr = cfg["device"]["address"]

    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Scanning for device (30s) — short-press the Slate to power on...")
    device = await BleakScanner.find_device_by_address(addr, timeout=30.0)
    if not device:
        print("Device not found.")
        sys.exit(1)

    print(f"Found: {device.name}")

    async with BleakClient(device) as client:
        slate = Slate(client, host_id)
        await slate.start()
        await slate.connect()
        await slate.setup()

        count = await slate.file_count()
        print(f"{count} drawing(s) on device.")

        if count == 0:
            return

        synced = 0
        while count > 0:
            _, ts = await slate.stroke_metadata()
            label = time.strftime('%Y%m%d_%H%M%S', time.gmtime(ts))
            out_path = out_dir / f"{label}.png"

            print(f"  [{synced + 1}/{count}] {label} — downloading...", end=' ', flush=True)
            raw = await slate.download_oldest()
            print(f"{len(raw)} bytes — parsing...", end=' ', flush=True)

            strokes = parse_strokes(raw)
            print(f"{len(strokes)} strokes — rendering...", end=' ', flush=True)

            render(strokes, out_path)
            print(f"saved → {out_path.name}")

            await slate.delete_oldest()

            synced += 1
            count -= 1

        print(f"\nDone — {synced} drawing(s) saved to {out_dir}/")


if __name__ == '__main__':
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT
    asyncio.run(main(out_dir))
