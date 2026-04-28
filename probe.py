"""
Raw BLE probe — connects and logs all notifications/indications while
also reading all Device Information characteristics.

Usage (device in pairing mode — long press):
  python probe.py
"""

import asyncio
import sys
from datetime import datetime
from bleak import BleakClient, BleakScanner

DEVICE_ADDR = "4D0C6741-2678-949F-1C7A-021B1C283EDD"

# All notify/indicate characteristics to subscribe to
WATCH = [
    ("ffee0003", "ffee0003-bbaa-9988-7766-554433221100"),  # wacom data stream
    ("ffee0004", "ffee0004-bbaa-9988-7766-554433221100"),  # wacom ACK/status
    ("uart_tx",  "6e400003-b5a3-f393-e0a9-e50e24dcca9e"),  # nordic uart TX
    ("events",   "3a340721-c572-11e5-86c5-0002a5d5c51b"),  # unknown events
    ("button",   "00001524-1212-efde-1523-785feabcd123"),  # button
    ("battery",  "00002a19-0000-1000-8000-00805f9b34fb"),  # battery level
]

DEVICE_INFO = {
    "Manufacturer": "00002a29-0000-1000-8000-00805f9b34fb",
    "Model":        "00002a24-0000-1000-8000-00805f9b34fb",
    "Serial":       "00002a25-0000-1000-8000-00805f9b34fb",
    "Firmware":     "00002a26-0000-1000-8000-00805f9b34fb",
    "Software":     "00002a28-0000-1000-8000-00805f9b34fb",
}


def log(name: str, data: bytes):
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    print(f"[{ts}] {name:12s}  len={len(data):3d}  hex={data.hex()}  raw={data!r}")


def make_handler(name):
    def handler(sender, data):
        log(name, data)
    return handler


async def main():
    print(f"Scanning for {DEVICE_ADDR} (30s) — long-press the Slate now if not in pairing mode...")
    device = await BleakScanner.find_device_by_address(DEVICE_ADDR, timeout=30.0)
    if not device:
        print("Device not found. Make sure it's in pairing/advertising mode (long press).")
        sys.exit(1)

    print(f"Found: {device.name} — connecting...\n")

    async with BleakClient(device) as client:
        print("Connected.\n")

        # Read device info
        print("=== Device Information ===")
        for label, uuid in DEVICE_INFO.items():
            try:
                val = await client.read_gatt_char(uuid)
                print(f"  {label}: {val.decode('utf-8', errors='replace')}")
            except Exception as e:
                print(f"  {label}: ERROR {e}")
        print()

        # Subscribe to all notify/indicate characteristics
        print("=== Subscribing to notifications ===")
        for name, uuid in WATCH:
            try:
                await client.start_notify(uuid, make_handler(name))
                print(f"  Subscribed: {name} ({uuid})")
            except Exception as e:
                print(f"  FAILED {name}: {e}")
        print()

        print("=== Listening — press the Slate button or interact with it ===")
        print("    (Ctrl+C to stop)\n")
        try:
            await asyncio.sleep(120)
        except KeyboardInterrupt:
            print("\nStopped.")


if __name__ == "__main__":
    asyncio.run(main())
