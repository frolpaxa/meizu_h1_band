#!/usr/bin/env python3
"""Probe candidate clock-setting commands for Meizu H1."""
import asyncio
import sys
from datetime import datetime

from bleak import BleakClient

import os

ADDR = os.environ["MEIZU_BAND_ADDRESS"]
TS = int(datetime.now().timestamp())
now = datetime.fromtimestamp(TS)
print(f"TS={TS} local={now}", flush=True)

events = []

def make_cb():
    def cb(char, data):
        events.append((char.handle, bytes(data).hex()))
        print(f"   EVT h{char.handle}: {bytes(data).hex()}", flush=True)
    return cb

async def main():
    async with BleakClient(ADDR, timeout=30) as c:
        print(f"Connected {c.name}", flush=True)
        for h in (10, 16, 22, 29, 32):
            ch = c.services.get_characteristic(h)
            if ch and {"notify", "indicate"}.intersection(ch.properties):
                await c.start_notify(ch, make_cb())
                print(f" sub h{h}", flush=True)

        async def read_regs():
            vals = {}
            for h in (27, 29, 32):
                ch = c.services.get_characteristic(h)
                try:
                    vals[h] = bytes(await asyncio.wait_for(c.read_gatt_char(ch), 5)).hex()
                except Exception as e:
                    vals[h] = "ERR" + str(e)[:30]
            return vals

        base = await read_regs()
        print("BASE", base, flush=True)

        h25 = c.services.get_characteristic(25)
        h32 = c.services.get_characteristic(32)
        h13 = c.services.get_characteristic(13)
        h19 = c.services.get_characteristic(19)

        t4le = (TS & 0xFFFFFFFF).to_bytes(4, 'little')
        t4be = (TS & 0xFFFFFFFF).to_bytes(4, 'big')
        t6le = TS.to_bytes(6, 'little')
        t8le = TS.to_bytes(8, 'little')
        hms = bytes((now.hour, now.minute, now.second))
        dt8 = now.strftime("%Y%m%d%H%M%S").encode()

        candidates = [
            ("h25:[01]",            h25, bytes([0x01])),
            ("h25:[02]",            h25, bytes([0x02])),
            ("h25:[03]",            h25, bytes([0x03])),
            ("h25:[54]",            h25, bytes([0x54])),
            ("h25:ts4LE",           h25, t4le),
            ("h25:ts4BE",           h25, t4be),
            ("h25:ts6LE",           h25, t6le),
            ("h25:ts8LE",           h25, t8le),
            ("h25:[01,ts4LE]",      h25, bytes([0x01]) + t4le),
            ("h25:[02,ts4LE]",      h25, bytes([0x02]) + t4le),
            ("h25:[54,ts4LE]",      h25, bytes([0x54]) + t4le),
            ("h25:[54,ts4BE]",      h25, bytes([0x54]) + t4be),
            ("h25:[04,ts4LE]",      h25, bytes([0x04]) + t4le),
            ("h25:[01,hms]",        h25, bytes([0x01]) + hms),
            ("h25:[02,hms]",        h25, bytes([0x02]) + hms),
            ("h25:dt8",             h25, dt8),
            ("h25:[01,ts4LE]+trg",  h25, bytes([0x01]) + t4le),
            ("h25:[02,ts4LE]+trg",  h25, bytes([0x02]) + t4le),
            ("h25:[54,ts4LE]+trg",  h25, bytes([0x54]) + t4le),
            ("h13:[01]",            h13, bytes([0x01])),
            ("h13:[02]",            h13, bytes([0x02])),
            ("h13:ts4LE",           h13, t4le),
            ("h13:[01,ts4LE]",      h13, bytes([0x01]) + t4le),
            ("h13:[02,ts4LE]",      h13, bytes([0x02]) + t4le),
            ("h19:[01]",            h19, bytes([0x01])),
            ("h19:[02]",            h19, bytes([0x02])),
            ("h19:ts4LE",           h19, t4le),
            ("h19:[01,ts4LE]",      h19, bytes([0x01]) + t4le),
        ]

        # If an h25 command works, append the trigger and check again.
        for name, ch, payload in candidates:
            events.clear()
            try:
                await c.write_gatt_char(ch, payload)
            except Exception as e:
                print(f"{name}: WRITE ERR {e}", flush=True)
                continue
            if name.endswith("+trg"):
                await c.write_gatt_char(h32, bytes([0x01]))
            print(f"-> {name} {payload.hex()}", flush=True)
            await asyncio.sleep(2.0)
            regs = await read_regs()
            changed = {k: (regs[k], base.get(k)) for k in regs if regs[k] != base.get(k)}
            if events or changed:
                print(f"    ** REACTION events={events} changed={changed}", flush=True)
            await asyncio.sleep(0.3)
        print("DONE", flush=True)

asyncio.run(main())
sys.exit(0)
