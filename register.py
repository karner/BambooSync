"""
One-time registration script for Wacom Bamboo Slate.

This gives the device a persistent host identity so future connections
work with a short button press instead of long-press pairing mode.

Usage:
  1. Long-press the Slate button until it flashes (pairing mode)
  2. python register.py
  3. When prompted, press the button once on the Slate
"""

import asyncio
import os
import sys
import tomllib
from bleak import BleakClient, BleakScanner

DEVICE_ADDR  = "4D0C6741-2678-949F-1C7A-021B1C283EDD"
UART_CMD     = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"  # host → device (write)
UART_RESP    = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"  # device → host (notify)

CONFIG_FILE  = os.path.join(os.path.dirname(__file__), "config.toml")

OPCODE_REGISTER_PRESS = 0xe7   # Slate: send host_id, then user presses button
OPCODE_CONNECT        = 0xe6   # Slate: normal connect after registration
REPLY_REGISTERED      = 0xe4   # device confirms registration
REPLY_CONNECT_OK      = 0x50   # device confirms normal connect


def load_host_id() -> bytes:
    """Load or generate the persistent 6-byte host identifier."""
    try:
        with open(CONFIG_FILE, "rb") as f:
            cfg = tomllib.load(f)
        host_id_hex = cfg.get("host", {}).get("id", "")
        if host_id_hex and len(host_id_hex) == 12:
            return bytes.fromhex(host_id_hex)
    except Exception:
        pass

    # Generate a new host ID and save it
    host_id = os.urandom(6)
    _save_host_id(host_id.hex())
    print(f"Generated new host ID: {host_id.hex()} (saved to config.toml)")
    return host_id


def _save_host_id(hex_id: str):
    """Write host id into config.toml, replacing any existing value."""
    with open(CONFIG_FILE, "r") as f:
        text = f.read()
    if 'id = ""' in text:
        text = text.replace('id = ""', f'id = "{hex_id}"')
    else:
        text += f'\n[host]\nid = "{hex_id}"\n'
    with open(CONFIG_FILE, "w") as f:
        f.write(text)


async def main():
    host_id = load_host_id()
    print(f"Host ID: {host_id.hex()}")

    print(f"\nScanning for {DEVICE_ADDR} (30s) — make sure Slate is in pairing mode (long press)...")
    device = await BleakScanner.find_device_by_address(DEVICE_ADDR, timeout=30.0)
    if not device:
        print("Device not found.")
        sys.exit(1)

    reply_event = asyncio.Event()
    reply_opcode = [None]

    def on_response(sender, data: bytearray):
        opcode = data[0]
        print(f"  ← device: opcode=0x{opcode:02x}  {data.hex()}")
        reply_opcode[0] = opcode
        reply_event.set()

    print(f"Found: {device.name} — connecting...")
    async with BleakClient(device) as client:
        print("Connected.\n")
        await client.start_notify(UART_RESP, on_response)

        # Send REGISTER_PRESS_BUTTON: [opcode, len=6, host_id_bytes...]
        cmd = bytes([OPCODE_REGISTER_PRESS, 6]) + host_id
        print(f"→ Sending REGISTER_PRESS_BUTTON: {cmd.hex()}")
        await client.write_gatt_char(UART_CMD, cmd, response=False)

        print("\nPress the button on the Slate now...")
        try:
            await asyncio.wait_for(reply_event.wait(), timeout=30.0)
        except asyncio.TimeoutError:
            print("Timed out waiting for button press.")
            sys.exit(1)

        if reply_opcode[0] == REPLY_REGISTERED:
            print("\nRegistration successful!")
            print("Future connections: short press to power on, then run connect.py")
        else:
            print(f"\nUnexpected reply opcode: 0x{reply_opcode[0]:02x}")
            sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
