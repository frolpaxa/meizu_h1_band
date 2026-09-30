# Meizu H1: BLE Protocol Notes

## Verified behavior

On September 30, 2026, the band clock was synchronized with the computer's local time (Europe/Moscow, UTC+3). The band acknowledged bonding, activation, the time update, and the timezone update. The device serial number is intentionally omitted. These acknowledgements document that session only; they do not describe the device's current state.

## Protocol source

The text API was identified in the Meizu Band Android application, version `1.0.24 (161208)`, package `com.meizu.smart.wristband`. The APK is [`meizu-band-1.0.24.apk`](./meizu-band-1.0.24.apk); its MD5 is `3dfaaa5d260dd83f2d404ab8a8667327`, matching the checksum listed on the [APK download page](https://www.962.net/azsoft/147229.html).

Class `FBBleApi1` defines these UUIDs for the text API:

| Role | UUID |
|---|---|
| BLE service | `0000190a-0000-1000-8000-00805f9b34fb` |
| Command write characteristic | `00000001-0000-1000-8000-00805f9b34fb` |
| Response notify characteristic | `00000002-0000-1000-8000-00805f9b34fb` |

The first script version sent time data to `FEC7` (handle 25) and `01` to `FEA2` (handle 32). That is not the clock-setting command used by the APK. Vibration from that attempt did not prove that the time was accepted; `set_time` now uses the text protocol below.

## App command sequence

The app's normal binding procedure uses this sequence:

1. `AT+BOND\r\n` — bind the device. Expected response: `AT+BOND:OK\r\n`.
2. `AT+SN\r\n` — request the serial number. The value is deliberately not recorded here.
3. `AT+ACT=1\r\n` — enable the device.
4. `AT+DT=yyyyMMddHHmmss\r\n` — set local date and time, for example `AT+DT=20260930225216\r\n`.
5. `AT+TIMEZONE=<offset_in_seconds>\r\n` — set the UTC offset. For UTC+3, use `AT+TIMEZONE=10800\r\n`.

The current timezone query is `AT+TIMEZONE\r\n`; a verified response had the form `AT+TIMEZONE:10800\r\n`.

The APK splits BLE payloads into consecutive chunks of at most 20 bytes. For the 22-byte time command, it sends the first 20 bytes separately from the final `\r\n`. Keep this in mind when implementing another BLE client.

## Verification limits

- A BLE write without an application response confirms only delivery at the GATT layer. Subscribe to notify UUID `00000002` and wait for the text response to verify the command.
- The `AT+DT:<value>` response confirmed the time update; vibration or a successful `write_gatt_char` return alone did not.
- `set_time` in [`meizu_band.py`](./meizu_band.py) subscribes to notifications, writes through UUID `00000001` in 20-byte chunks, and waits for matching responses. Without `--timestamp`, it uses the computer's current local time and UTC offset.

## Examples

Run commands from the project directory. First discover the band's current BLE address with `scan`, then pass it to the desired command:

```sh
python3 meizu_band.py scan
python3 meizu_band.py set_time <DEVICE_ADDRESS>
```

To set a specific moment, pass a Unix timestamp in seconds:

```sh
python3 meizu_band.py set_time <DEVICE_ADDRESS> --timestamp 1790798400
```

The script prints each response and fails if a response does not arrive within 10 seconds. Keep the band nearby and available for a BLE connection during synchronization.

### Wrist-lift screen activation

Enable the feature all day:

```sh
python3 meizu_band.py set_handup <DEVICE_ADDRESS>
```

By default, the script sends `AT+HANDSUP=1,0000,2359`. Set a time range with `--start 07:00 --end 23:00`. Use `--off` to disable the feature for the selected interval.

### Text notification

The APK sends SMS text as the second field of `AT+PUSH`; the final field `1` selects the SMS notification type. The script can send a short test message:

```sh
python3 meizu_band.py notify <DEVICE_ADDRESS> "Test message"
```

Commas and line breaks are rejected because the APK does not escape field separators. The band displays this as an SMS notification. No arbitrary notification type with a separate sender or app name was found in the APK.

### Alarms

Disable both alarm slots:

```sh
python3 meizu_band.py clear_alarms <DEVICE_ADDRESS>
```

Set one weekday alarm at 07:30 (the command also disables the second slot):

```sh
python3 meizu_band.py set_alarm <DEVICE_ADDRESS> 07:30 --repeat weekdays
```

`--repeat` accepts `once`, `daily`, or `weekdays`. The APK stores alarms in the phone's local database, so these script commands do not update that list; a later app sync may overwrite the band settings. The firmware response to alarm commands has not been verified: the script confirms only that the BLE write succeeded. The discovered API cannot read the alarm list from the band.

## `FBBleApi1` command catalog

These text commands were found in `FBBleApi1` in APK v1.0.24. Angle-bracketed items are arguments concatenated by the app. Commands end in `\r\n` and are sent as UTF-8. Descriptions and argument types are inferred from method names and caller code; unknown value ranges are called out. A command's presence in the APK does not prove support in every firmware version.

### Connection and state

| Command | APK method | Purpose |
|---|---|---|
| `AT+BOND` | `bind` | Bind the device. The band returned `AT+BOND:OK`. |
| `AT+SN` | `getSn` | Request the serial number. |
| `AT+ACT=1` | `enable` | Activate/enable the device. Verified response: `AT+ACT:1`. |
| `AT+VER` | `getVer` | Request the firmware version. |
| `AT+BATT` | `getBattery` | Request the battery level. |
| `AT+OFF` | `turnOff` | Power-off command; unverified. |
| `AT+RESETREAS` | `resetRAES` | Related to reset reason; its exact read/write behavior is unclear and unverified. |

### Clock and display

| Command | APK method | Purpose / format |
|---|---|---|
| `AT+DT=<yyyyMMddHHmmss>` | `setTime` | Set local date and time, e.g. `AT+DT=20260930225216`. A response `AT+DT:<value>` confirmed it. |
| `AT+TIMEZONE` | `getTimeZone` | Request timezone offset. A verified response was `AT+TIMEZONE:10800`. |
| `AT+TIMEZONE=<seconds>` | `setTimeZone` | Set UTC offset in seconds; UTC+3 is `10800`. Verified on the band. |
| `AT+TIMEFORMAT=<int>` | `setTWhour` | Set time format; code mappings are unknown. |
| `AT+TIMEDISPLAY=<string>` | `setTimeDisplay` | Configure time display; accepted values are unknown. |
| `AT+HANDSUP=<enabled>,<start HHMM>,<end HHMM>` | `setHandup` | Control wrist-lift screen activation. The app uses `1`/`0` and 24-hour `HHMM`, e.g. `AT+HANDSUP=1,0800,2300`. |

### Activity, health, and workouts

| Command | APK method | Purpose / format |
|---|---|---|
| `AT+PACE` | `getStep` | Request the step count. |
| `AT+PACE=<number>` | `setStep` | Write a step count; the APK left-pads it to five characters. Unverified. |
| `AT+TOPACE=<int>` | `enableStepReport` | Configure a pace/step reporting parameter; units are unknown. |
| `AT+DEST=<string>` | `setSportAim` | Set an activity/sport goal; exact value format is unknown. |
| `AT+DATA` | `generateData` | Request data. |
| `AT+DATA=<int>` | `requestData` | Request a data type; type codes are unknown. |
| `AT+STEPSTORE` | `stepStore` | Step-storage operation; exact meaning is unknown. |
| `AT+HEART=1` | `getStaticHeartRateBegin` | Start a heart-rate measurement. |
| `AT+HEART=0` | `getStaticHeartRateEnd` | Stop a heart-rate measurement. |
| `AT+HRMONITOR=<string>` | `setHrMonitor` | Configure heart-rate monitoring; accepted values are unknown. |
| `AT+REALHEART=<int>,<int>` | `setRunSetting` | Configure live/workout heart-rate mode; both values and their meaning are unknown. |
| `AT+RUN=<int>` | `setRunParam` | Pass a running-mode parameter; accepted values are unknown. |
| `AT+RD=<string>,<string>` | `setRunInfo` | Pass two running-data fields. |
| `AT+SIT=<string>` | `setSitAlarm` | Configure an inactivity reminder; format is unknown. |
| `AT+HEIGHT=<int>` | `setHeight` | Set height; check units and range in the APK UI. |
| `AT+WEIGHT=<string>` | `setWeight` | Set weight; the app formats the value before sending. |
| `AT+SEX=<int>` | `setSex` | Pass a sex code; code mappings are not documented here. |

### Notifications, finding, and controls

| Command | APK method | Purpose / format |
|---|---|---|
| `AT+FINDBT=1` | `LocatingBand`, `setSmsIncoming` | Called by two differently named methods; exact semantics and values are unknown. |
| `AT+FINDPHONE=<int>` | `findPhoneFlag` | Phone-finding feature flag; values are unknown. |
| `AT+ANTI_LOST=<int>` | `setAntLostFlag` | Anti-loss feature flag; values are unknown. |
| `AT+CAMERA=<int>` | `setcCameraFlag` | Camera-control feature flag; values are unknown. |
| `AT+PUSH=<field1>,<field2>,<field3>,<field4>` | `pushMsg` | Send a typed notification with four fields. For SMS, the APK calls `pushMsg("0", text, "0", "1")`; supported apps use empty text and an app code in field 4. Separators are not escaped. |
| `AT+ZI` | `requestPushMsg1` | Message-related request; exact purpose is unknown. |
| `AT+MOTOR=<string>` | `setVibrate` | Control the vibration motor; accepted values are unknown. |

### Music, alarms, and system settings

| Command | APK method | Purpose / format |
|---|---|---|
| `AT+MUSIC=<int>` | `musicFlag` | Music feature flag; values are unknown. |
| `AT+MUSICPLY=<int>` | `syncMusicFlag` | Pass playback state; values are unknown. |
| `AT+SYN=<int>` | `setSyncFlag` | Set a sync flag; values are unknown. |
| `AT+ALARM=<string>` | `setAlarmClock1` | Write alarm slot 1. Format: `<enabled>,0,00,<7 weekday flags>1,HHMM`. One-shot 07:30 example: `AT+ALARM=1,0,00,00000001,0730`. |
| `AT+ALARM2=<string>` | `setAlarmClock2` | Write slot 2 in the same format. Clear it with flag `0`, e.g. `AT+ALARM2=0,0,00,00000001,0000`. |
| `AT+LAN=<int>` | `setLan` | Set language by numeric code. |

## Verified and unverified commands

Responses were received for `AT+BOND`, `AT+SN`, `AT+ACT=1`, `AT+DT=...`, `AT+TIMEZONE=...`, and the `AT+TIMEZONE` query. The alarm commands found in the APK are write commands; the API has no getter for alarms on the band. The APK screen reads the list from the phone's local database and serializes it to the band when saved. The repeat-flag order and firmware responses to alarm commands have not been verified on the device.
