#!/usr/bin/env python3
"""BLE diagnostics and time setting for Meizu Band H1."""
import argparse
import asyncio
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path


def positive(value):
    number = float(value)
    if not 0 < number <= 3600:
        raise argparse.ArgumentTypeError("Enter a number from 1 to 3600")
    return number


def clock_time(value):
    try:
        return datetime.strptime(value, "%H:%M").strftime("%H%M")
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Enter time in HH:MM format, for example 08:30") from exc


def notification_text(value):
    if any(char in value for char in ",\r\n"):
        raise argparse.ArgumentTypeError("Text must not contain commas or line breaks")
    return value


async def run(args):
    from bleak import BleakClient, BleakScanner

    if args.command == "scan":
        found = await BleakScanner.discover(timeout=args.timeout, return_adv=True)
        for device, adv in sorted(found.values(), key=lambda item: item[1].rssi, reverse=True):
            print(f"{device.address}  RSSI={adv.rssi:4}  {adv.local_name or device.name or '(unnamed)'}")
            print(f"  services={adv.service_uuids}")
        if not found:
            print("No devices found. Check Bluetooth and wake the band.")
        return

    if args.command == "set_time":
        try:
            local_time = (datetime.fromtimestamp(args.timestamp).astimezone()
                          if args.timestamp is not None else datetime.now().astimezone())
            timezone_seconds = int(local_time.utcoffset().total_seconds())
            commands = [
                ("AT+BOND\r\n", "AT+BOND:"),
                ("AT+SN\r\n", "AT+SN:"),
                ("AT+ACT=1\r\n", "AT+ACT:"),
                (f"AT+DT={local_time:%Y%m%d%H%M%S}\r\n", "AT+DT:"),
                (f"AT+TIMEZONE={timezone_seconds}\r\n", "AT+TIMEZONE:"),
            ]
            service_uuid = "0000190a-0000-1000-8000-00805f9b34fb"
            write_uuid = "00000001-0000-1000-8000-00805f9b34fb"
            notify_uuid = "00000002-0000-1000-8000-00805f9b34fb"
            replies = asyncio.Queue()
            pending = bytearray()

            def on_notification(_characteristic, data):
                pending.extend(data)
                while b"\n" in pending:
                    line, _, remainder = pending.partition(b"\n")
                    pending[:] = remainder
                    decoded = line.decode("utf-8", errors="replace").strip("\r\x00 ")
                    if decoded:
                        replies.put_nowait(decoded)

            async with BleakClient(args.address, timeout=args.timeout) as client:
                command_char = client.services.get_characteristic(write_uuid)
                response_char = client.services.get_characteristic(notify_uuid)
                service = client.services.get_service(service_uuid)
                if service is None or command_char is None or response_char is None:
                    raise RuntimeError("Meizu Band protocol GATT service not found")
                await client.start_notify(response_char, on_notification)
                print(f"Connected to {args.address}; local time: {local_time:%Y-%m-%d %H:%M:%S} "
                      f"(UTC{timezone_seconds // 3600:+03d}:{abs(timezone_seconds) % 3600 // 60:02d})")
                try:
                    for command, expected_prefix in commands:
                        payload = command.encode("utf-8")
                        for offset in range(0, len(payload), 20):
                            await client.write_gatt_char(command_char, payload[offset:offset + 20], response=True)
                            await asyncio.sleep(0.1)
                        deadline = asyncio.get_running_loop().time() + args.reply_timeout
                        while True:
                            remaining = deadline - asyncio.get_running_loop().time()
                            if remaining <= 0:
                                raise TimeoutError(f"No response to {command.strip()}")
                            reply = await asyncio.wait_for(replies.get(), remaining)
                            if reply.startswith(expected_prefix):
                                break
                        print(f"{command.strip()} → {reply}")
                        if command.startswith("AT+BOND") and not reply.endswith("OK"):
                            raise RuntimeError(f"Band did not confirm bonding: {reply}")
                finally:
                    if client.is_connected:
                        await client.stop_notify(response_char)
            return
        except Exception as e:
            print(f"Error setting time: {e}")
            raise

    if args.command == "set_handup":
        enabled = 0 if args.off else 1
        command = f"AT+HANDSUP={enabled},{args.start},{args.end}\r\n"
        service_uuid = "0000190a-0000-1000-8000-00805f9b34fb"
        write_uuid = "00000001-0000-1000-8000-00805f9b34fb"
        notify_uuid = "00000002-0000-1000-8000-00805f9b34fb"
        replies = asyncio.Queue()
        pending = bytearray()

        def on_notification(_characteristic, data):
            pending.extend(data)
            while b"\n" in pending:
                line, _, remainder = pending.partition(b"\n")
                pending[:] = remainder
                decoded = line.decode("utf-8", errors="replace").strip("\r\x00 ")
                if decoded:
                    replies.put_nowait(decoded)

        async with BleakClient(args.address, timeout=args.timeout) as client:
            command_char = client.services.get_characteristic(write_uuid)
            response_char = client.services.get_characteristic(notify_uuid)
            service = client.services.get_service(service_uuid)
            if service is None or command_char is None or response_char is None:
                raise RuntimeError("Meizu Band protocol GATT service not found")
            await client.start_notify(response_char, on_notification)
            try:
                for payload_text, expected_prefix in (
                    ("AT+BOND\r\n", "AT+BOND:"),
                    (command, "AT+HANDSUP:"),
                ):
                    payload = payload_text.encode("utf-8")
                    for offset in range(0, len(payload), 20):
                        await client.write_gatt_char(command_char, payload[offset:offset + 20], response=True)
                        await asyncio.sleep(0.1)
                    deadline = asyncio.get_running_loop().time() + args.reply_timeout
                    while True:
                        remaining = deadline - asyncio.get_running_loop().time()
                        if remaining <= 0:
                            raise TimeoutError(f"No response to {payload_text.strip()}")
                        reply = await asyncio.wait_for(replies.get(), remaining)
                        if reply.startswith(expected_prefix):
                            break
                    print(f"{payload_text.strip()} → {reply}")
                    if payload_text.startswith("AT+BOND") and not reply.endswith("OK"):
                        raise RuntimeError(f"Band did not confirm bonding: {reply}")
            finally:
                if client.is_connected:
                    await client.stop_notify(response_char)
        return

    if args.command == "notify":
        command = f"AT+PUSH=0,{args.message},0,1\r\n"
        service_uuid = "0000190a-0000-1000-8000-00805f9b34fb"
        write_uuid = "00000001-0000-1000-8000-00805f9b34fb"
        notify_uuid = "00000002-0000-1000-8000-00805f9b34fb"
        replies = asyncio.Queue()
        pending = bytearray()

        def on_notification(_characteristic, data):
            pending.extend(data)
            while b"\n" in pending:
                line, _, remainder = pending.partition(b"\n")
                pending[:] = remainder
                decoded = line.decode("utf-8", errors="replace").strip("\r\x00 ")
                if decoded:
                    replies.put_nowait(decoded)

        async with BleakClient(args.address, timeout=args.timeout) as client:
            command_char = client.services.get_characteristic(write_uuid)
            response_char = client.services.get_characteristic(notify_uuid)
            service = client.services.get_service(service_uuid)
            if service is None or command_char is None or response_char is None:
                raise RuntimeError("Meizu Band protocol GATT service not found")
            await client.start_notify(response_char, on_notification)
            try:
                for payload_text, expected_prefix in (
                    ("AT+BOND\r\n", "AT+BOND:"),
                    (command, "AT+PUSH:"),
                ):
                    payload = payload_text.encode("utf-8")
                    for offset in range(0, len(payload), 20):
                        await client.write_gatt_char(command_char, payload[offset:offset + 20], response=True)
                        await asyncio.sleep(0.1)
                    deadline = asyncio.get_running_loop().time() + args.reply_timeout
                    while True:
                        remaining = deadline - asyncio.get_running_loop().time()
                        if remaining <= 0:
                            raise TimeoutError(f"No response to {payload_text.strip()}")
                        reply = await asyncio.wait_for(replies.get(), remaining)
                        if reply.startswith(expected_prefix):
                            break
                    print(f"{payload_text.strip()} → {reply}")
                    if payload_text.startswith("AT+BOND") and not reply.endswith("OK"):
                        raise RuntimeError(f"Band did not confirm bonding: {reply}")
            finally:
                if client.is_connected:
                    await client.stop_notify(response_char)
        return

    if args.command in ("set_alarm", "clear_alarms"):
        service_uuid = "0000190a-0000-1000-8000-00805f9b34fb"
        write_uuid = "00000001-0000-1000-8000-00805f9b34fb"
        notify_uuid = "00000002-0000-1000-8000-00805f9b34fb"
        disabled = "0,0,00,00000001,0000"
        if args.command == "clear_alarms":
            commands = [f"AT+ALARM={disabled}\r\n", f"AT+ALARM2={disabled}\r\n"]
        else:
            repeat_bits = {
                "once": "0000000",
                "daily": "1111111",
                "weekdays": "0111110",  # UI order: Sunday through Saturday
            }[args.repeat]
            commands = [
                f"AT+ALARM2={disabled}\r\n",
                f"AT+ALARM=1,0,00,{repeat_bits}1,{args.time}\r\n",
            ]
        replies = asyncio.Queue()
        pending = bytearray()

        def on_notification(_characteristic, data):
            pending.extend(data)
            while b"\n" in pending:
                line, _, remainder = pending.partition(b"\n")
                pending[:] = remainder
                decoded = line.decode("utf-8", errors="replace").strip("\r\x00 ")
                if decoded:
                    replies.put_nowait(decoded)

        async with BleakClient(args.address, timeout=args.timeout) as client:
            command_char = client.services.get_characteristic(write_uuid)
            response_char = client.services.get_characteristic(notify_uuid)
            service = client.services.get_service(service_uuid)
            if service is None or command_char is None or response_char is None:
                raise RuntimeError("Meizu Band protocol GATT service not found")
            await client.start_notify(response_char, on_notification)
            try:
                bond = b"AT+BOND\r\n"
                for offset in range(0, len(bond), 20):
                    await client.write_gatt_char(command_char, bond[offset:offset + 20], response=True)
                    await asyncio.sleep(0.1)
                deadline = asyncio.get_running_loop().time() + args.reply_timeout
                while True:
                    remaining = deadline - asyncio.get_running_loop().time()
                    if remaining <= 0:
                        raise TimeoutError("No response to AT+BOND")
                    reply = await asyncio.wait_for(replies.get(), remaining)
                    if reply.startswith("AT+BOND:"):
                        break
                if not reply.endswith("OK"):
                    raise RuntimeError(f"Band did not confirm bonding: {reply}")
                print(f"AT+BOND → {reply}")
                for command in commands:
                    payload = command.encode("utf-8")
                    for offset in range(0, len(payload), 20):
                        await client.write_gatt_char(command_char, payload[offset:offset + 20], response=True)
                        await asyncio.sleep(0.1)
                    print(f"Write sent: {command.strip()} (firmware acknowledgement not verified)")
            finally:
                if client.is_connected:
                    await client.stop_notify(response_char)
        return

    report = {"created_utc": datetime.now(timezone.utc).isoformat(),
              "platform": platform.platform(), "address": args.address,
              "services": [], "notifications": []}
    try:
        device = await BleakScanner.find_device_by_address(args.address, timeout=args.timeout)
        if device is None:
            raise RuntimeError("Device not found. Run scan again near the powered-on band.")
        report["name"] = device.name
        async with BleakClient(device, timeout=args.timeout) as client:
            print(f"Connected: {device.name or device.address}")
            for service in client.services:
                entry = {"uuid": service.uuid, "handle": service.handle, "characteristics": []}
                report["services"].append(entry)
                for char in service.characteristics:
                    item = {"uuid": char.uuid, "handle": char.handle,
                            "properties": list(char.properties),
                            "descriptors": [{"uuid": d.uuid, "handle": d.handle} for d in char.descriptors]}
                    entry["characteristics"].append(item)
                    print(f"  {char.handle}: {char.uuid} {','.join(char.properties)}")
                    if "read" in char.properties:
                        try:
                            data = bytes(await asyncio.wait_for(client.read_gatt_char(char), 10))
                            item["value_hex"] = data.hex()
                            if char.uuid == "00002a19-0000-1000-8000-00805f9b34fb" and len(data) == 1:
                                item["battery_percent"] = data[0]
                                print(f"    Battery: {data[0]}%")
                        except Exception as exc:
                            item["read_error"] = str(exc)

            if args.notify:
                def callback(char, data):
                    event = {"time_utc": datetime.now(timezone.utc).isoformat(),
                             "uuid": char.uuid, "handle": char.handle, "hex": bytes(data).hex()}
                    report["notifications"].append(event)
                    print(f"  notification {char.handle}: {event['hex']}")

                subscribed = []
                for handle in args.notify:
                    char = client.services.get_characteristic(handle)
                    if char is None or not {"notify", "indicate"}.intersection(char.properties):
                        raise ValueError(f"Characteristic {handle} is missing or does not support notifications")
                    await client.start_notify(char, callback)
                    subscribed.append(char)
                print(f"Listening for {args.seconds} seconds. You can press the band button.")
                try:
                    await asyncio.sleep(args.seconds)
                finally:
                    for char in subscribed:
                        if client.is_connected:
                            try:
                                await client.stop_notify(char)
                            except Exception:
                                pass
    except BaseException as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Report saved: {Path(args.output).resolve()}")


def main():
    parser = argparse.ArgumentParser(description="Control and diagnostics for Meizu Band H1")
    sub = parser.add_subparsers(dest="command", required=True)
    scan = sub.add_parser("scan", help="Find nearby BLE devices")
    scan.add_argument("--timeout", type=positive, default=15)
    set_time = sub.add_parser("set_time", help="Set the band clock")
    set_time.add_argument("address", help="Device address from scan")
    set_time.add_argument("--timestamp", type=int, help="Unix timestamp; defaults to current local time")
    set_time.add_argument("--timeout", type=positive, default=30, help="Connection timeout")
    set_time.add_argument("--reply-timeout", type=positive, default=10, help="Timeout for each command response")
    handup = sub.add_parser("set_handup", help="Enable or disable wrist-lift screen activation")
    handup.add_argument("address", help="Device address from scan")
    handup.add_argument("--start", type=clock_time, default="00:00", help="Start time HH:MM (default: 00:00)")
    handup.add_argument("--end", type=clock_time, default="23:59", help="End time HH:MM (default: 23:59)")
    handup.add_argument("--off", action="store_true", help="Disable wrist-lift activation")
    handup.add_argument("--timeout", type=positive, default=30, help="Connection timeout")
    handup.add_argument("--reply-timeout", type=positive, default=10, help="Timeout for each command response")
    notify = sub.add_parser("notify", help="Show text on the band as an SMS notification")
    notify.add_argument("address", help="Device address from scan")
    notify.add_argument("message", type=notification_text, help="Text without commas or line breaks")
    notify.add_argument("--timeout", type=positive, default=30, help="Connection timeout")
    notify.add_argument("--reply-timeout", type=positive, default=10, help="Timeout for each command response")
    alarm_clear = sub.add_parser("clear_alarms", help="Disable both alarm slots")
    alarm_clear.add_argument("address", help="Device address from scan")
    alarm_clear.add_argument("--timeout", type=positive, default=30, help="Connection timeout")
    alarm_clear.add_argument("--reply-timeout", type=positive, default=10, help="Timeout for the bonding response")
    alarm_set = sub.add_parser("set_alarm", help="Set one alarm and disable the other")
    alarm_set.add_argument("address", help="Device address from scan")
    alarm_set.add_argument("time", type=clock_time, help="Time HH:MM")
    alarm_set.add_argument("--repeat", choices=("once", "daily", "weekdays"), default="once",
                           help="Repeat: once, daily, or weekdays (Monday-Friday)")
    alarm_set.add_argument("--timeout", type=positive, default=30, help="Connection timeout")
    alarm_set.add_argument("--reply-timeout", type=positive, default=10, help="Timeout for the bonding response")
    inspect = sub.add_parser("inspect", help="Connect and save a GATT report")
    inspect.add_argument("address", help="Device address or UUID from scan")
    inspect.add_argument("--timeout", type=positive, default=30)
    inspect.add_argument("--output", default="meizu_report.json")
    inspect.add_argument("--notify", type=lambda x: int(x, 0), action="append",
                         help="Characteristic handle to subscribe to; may be repeated")
    inspect.add_argument("--seconds", type=positive, default=30)
    args = parser.parse_args()
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        print("Stopped.", file=sys.stderr)
        return 130
    except ImportError:
        print("Install the dependency: python3 -m pip install bleak", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
