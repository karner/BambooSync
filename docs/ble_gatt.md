# BLE GATT Map — Wacom Bamboo Slate

**Device address (macOS):** `4D0C6741-2678-949F-1C7A-021B1C283EDD`  
**Discovered:** 2026-04-27

---

## Service Map

| Service UUID | Name | Role |
|---|---|---|
| `ffee0001-bbaa-9988-7766-554433221100` | Wacom Proprietary | **Offline data — primary target** |
| `6e400001-b5a3-f393-e0a9-e50e24dcca9e` | Nordic UART | Secondary protocol channel |
| `3a340720-c572-11e5-86c5-0002a5d5c51b` | Unknown (Wacom?) | Possibly real-time pen events |
| `00001523-1212-efde-1523-785feabcd123` | Nordic LED Button | Button press + LED control |
| `0000180f-0000-1000-8000-00805f9b34fb` | Battery Service | Battery level |
| `0000180a-0000-1000-8000-00805f9b34fb` | Device Information | Manufacturer, firmware, etc. |
| `00001530-1212-efde-1523-785feabcd123` | DFU | Firmware update — do not touch |

---

## Wacom Proprietary Service (`ffee0001-...`)

This is the primary channel for offline note retrieval. The write+notify+indicate pattern is a classic request/response split:

| Characteristic | UUID | Properties | Role (hypothesis) |
|---|---|---|---|
| `ffee0002` | `ffee0002-bbaa-9988-7766-554433221100` | write-without-response, write | Send commands to device |
| `ffee0003` | `ffee0003-bbaa-9988-7766-554433221100` | notify | Streaming data from device |
| `ffee0004` | `ffee0004-bbaa-9988-7766-554433221100` | indicate | ACK / status responses |

**Protocol approach:**
1. Subscribe to `ffee0003` (notify) and `ffee0004` (indicate)
2. Write command bytes to `ffee0002`
3. Data streams in on `ffee0003`; completion/ACK arrives on `ffee0004`

---

## Nordic UART Service (`6e400001-...`)

| Characteristic | UUID | Properties | Role |
|---|---|---|---|
| RX | `6e400002-b5a3-f393-e0a9-e50e24dcca9e` | write-without-response, write | Host → Device |
| TX | `6e400003-b5a3-f393-e0a9-e50e24dcca9e` | notify | Device → Host |

May be used for a handshake/session setup before switching to the `ffee` service, or may be an alternative data path. **Needs probing.**

---

## Unknown Notify-Only Service (`3a340720-...`)

| Characteristic | UUID | Properties | Role |
|---|---|---|---|
| `3a340721` | `3a340721-c572-11e5-86c5-0002a5d5c51b` | notify | Unknown — possibly real-time stroke events |

Only one characteristic, notify-only — likely a passive event stream (button press, pen-down, sync trigger). Subscribe and observe while interacting with the device.

---

## Characteristic Role Corrections (from tuhi source)

| Our label | UUID | Actual role |
|---|---|---|
| `uart_rx` (our label) | `6e400002` | **Host → Device** (write); tuhi calls this UART TX |
| `uart_tx` (our label) | `6e400003` | **Device → Host** (notify); tuhi calls this UART RX |
| `button` (our label) | `00001524` | **Live pen data** — not a button. `WACOM_CHRC_LIVE_PEN_DATA_UUID` in tuhi |

All protocol commands go to `6e400002`; all protocol responses come back on `6e400003`.

---

## Protocol: NordicData Packet Format

All messages to/from the device use this 3-part frame:

```
[opcode, len(args), ...args]
```

Written to `6e400002`. Responses arrive on `6e400003`.

---

## Protocol: Registration (one-time)

Registration gives the device a host identity so it can reconnect without pairing mode.

| Step | Action | Bytes written to `6e400002` |
|---|---|---|
| 1 | Send REGISTER_PRESS_BUTTON | `[0xe7, 0x06, <host_id 6 bytes>]` |
| 2 | User presses physical button | — |
| 3 | Device replies on `6e400003` | opcode `0xe4` = Slate confirmed |
| 4 | REGISTER_COMPLETE | NOOP for Slate (nothing to send) |

**host_id**: a stable 6-byte identifier for this host (store in config, reuse forever).

---

## Protocol: Connect (every session after registration)

| Step | Action | Bytes written to `6e400002` |
|---|---|---|
| 1 | Send CONNECT | `[0xe6, 0x06, <host_id 6 bytes>]` |
| 2 | Device replies on `6e400003` | opcode `0x50` = success, `0x51` = auth error |

---

## Protocol: Download Stored Drawings

After a successful CONNECT:

| Step | Opcode | Args | Reply opcode |
|---|---|---|---|
| Set transfer channel to ffee0003 | `0xec` | `[0x06,0x00,0x00,0x00,0x00,0x00]` | `0xb3` (ACK) |
| Set mode to PAPER | `0xb1` | `[0x01]` | `0xb3` |
| Get available file count | `0xc1` | `[0x00]` | `0xc2` (count as little-u16) |
| Get strokes (count + timestamp) | `0xcc` | `[0x00]` | `0xcf` |
| Download oldest file | `0xc3` | `[0x00]` | `0xc8` (data on ffee0003) |
| Wait for end of read | — | — | `0xc8 0xed` then CRC |
| Delete oldest file | `0xca` | `[0x00]` | `0xb3` |

Repeat get-strokes → download → delete until file count = 0.

---

## Observed Events on `3a340721` (SYSEVENT)

| Bytes | Meaning |
|---|---|
| `ef 01 00` | Device ready / waiting for handshake (fires on subscription) |
| `f1 02 XX 00` | Battery report — XX = level as integer (0x64 = 100%) |
