#!/usr/bin/env python3
"""Probe: is the Xiaomi pairing path on h25 alive? Send CMD_REQUEST_RANDOM=0x02."""
import asyncio
from bleak import BleakClient

import os

ADDR = os.environ["MEIZU_BAND_ADDRESS"]
AUTH_HANDLE = 29
WRITE_HANDLE = 25
events = []
def cb(char, data):
    events.append((char.handle, bytes(data).hex()))

async def main():
    async with BleakClient(ADDR, timeout=30) as c:
        print(f"Connected {c.name}", flush=True)
        ch29 = c.services.get_characteristic(AUTH_HANDLE)
        ch25 = c.services.get_characteristic(WRITE_HANDLE)
        await c.start_notify(ch29, cb)
        print("subscribed h29", flush=True)

        async def wait(n=3.0):
            events.clear()
            try:
                await asyncio.sleep(n)
            finally:
                pass
            print(f"  events in window: {events}", flush=True)

        # 1) CMD_REQUEST_RANDOM
        print("-- CMD_REQUEST_RANDOM [02] --", flush=True)
        try:
            await c.write_gatt_char(ch25, bytes([0x02]))
        except Exception as e:
            print(f"  WRITE ERR {e}", flush=True)
        await wait(3.5)

        # 2) try CMD_SEND_KEY with placeholder (just to see if it errors)
        print("-- CMD_SEND_KEY [01 + 16 zero bytes] --", flush=True)
        try:
            await c.write_gatt_char(ch25, bytes([0x01]) + bytes(16))
        except Exception as e:
            print(f"  WRITE ERR {e}", flush=True)
        await wait(3.5)

        print("DONE", flush=True)

asyncio.run(main())
