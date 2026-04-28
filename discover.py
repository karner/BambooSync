"""
BLE discovery script for Wacom Bamboo Slate.

Usage:
  python discover.py          # scan and list all nearby BLE devices
  python discover.py <addr>   # connect to address and dump all GATT services/characteristics
"""

import asyncio
import sys
from bleak import BleakScanner, BleakClient


async def scan():
    print("Scanning for BLE devices (10s)...\n")
    devices = await BleakScanner.discover(timeout=10.0, return_adv=True)
    for device, adv in sorted(devices.values(), key=lambda d: d[1].rssi or -999, reverse=True):
        name = device.name or "(no name)"
        uuids = adv.service_uuids
        print(f"  {device.address}  RSSI={adv.rssi:4}  {name}")
        for u in uuids:
            print(f"              svc: {u}")


async def dump_gatt(address: str):
    print(f"\nConnecting to {address}...")
    async with BleakClient(address) as client:
        print(f"Connected: {client.is_connected}\n")
        for service in client.services:
            print(f"Service: {service.uuid}  ({service.description})")
            for char in service.characteristics:
                props = ", ".join(char.properties)
                print(f"  Char:  {char.uuid}  [{props}]  ({char.description})")
                for desc in char.descriptors:
                    print(f"    Desc: {desc.uuid}  ({desc.description})")
            print()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        asyncio.run(dump_gatt(sys.argv[1]))
    else:
        asyncio.run(scan())
