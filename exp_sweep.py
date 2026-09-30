#!/usr/bin/env python3
"""Sweep command byte values to find a reactive command."""
import asyncio
from bleak import BleakClient

import os

ADDR = os.environ["MEIZU_BAND_ADDRESS"]
events = []

def cb(char, data):
    events.append((char.handle, bytes(data).hex()))

async def main():
    async with BleakClient(ADDR, timeout=30) as c:
        print(f"Connected {c.name}", flush=True)
        for h in (10, 16, 22, 29, 32):
            ch = c.services.get_characteristic(h)
            if ch and {"notify", "indicate"}.intersection(ch.properties):
                await c.start_notify(ch, cb)

        async def regs():
            r = {}
            for h in (27, 29, 32):
                ch = c.services.get_characteristic(h)
                try:
                    r[h] = bytes(await asyncio.wait_for(c.read_gatt_char(ch), 3)).hex()
                except Exception:
                    r[h] = "ERR"
            return r

        base = await regs()
        print("BASE", base, flush=True)

        for label, h in [("h25", 25), ("h13", 13), ("h19", 19)]:
            ch = c.services.get_characteristic(h)
            print(f"-- sweep {label} (0x00-0x40) --", flush=True)
            for code in range(0x00, 0x41):
                events.clear()
                try:
                    await c.write_gatt_char(ch, bytes([code]))
                except Exception:
                    continue
                await asyncio.sleep(0.25)
                rn = await regs()
                changed = {k: (rn[k], base[k]) for k in rn if rn[k] != base[k]}
                if events or changed:
                    print(f"  code 0x{code:02X}: events={events} changed={changed}", flush=True)
        print("sweep done", flush=True)

        # Echo check: distinctive patterns.
        for label, h in [("h25", 25), ("h13", 13), ("h19", 19)]:
            ch = c.services.get_characteristic(h)
            for pattern in [0xDEADBEEF, 0x01234567, 0xABCDEF01]:
                events.clear()
                try:
                    await c.write_gatt_char(ch, pattern.to_bytes(4, "little"))
                except Exception as e:
                    print(f"  echo {label} 0x{pattern:08X}: ERR {e}", flush=True)
                    continue
                await asyncio.sleep(0.4)
                r = await regs()
                print(f"  echo {label} 0x{pattern:08X}: events={events} regs={r}", flush=True)
        print("DONE", flush=True)

asyncio.run(main())
