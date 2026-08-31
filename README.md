# Bamboo Slate Sync

> **⚠️ PRE-ALPHA / WORK IN PROGRESS**  
> This project is in active development and not yet ready for production use. Features may be incomplete, APIs may change, and bugs are expected. Use at your own risk.

A macOS menu bar app that watches for a Wacom Bamboo Slate over Bluetooth Low Energy (BLE), downloads stored handwritten notes, renders them as images, and transcribes them with a local AI model into your notes vault.

## Overview

The app sits in the menu bar and watches for your Slate. When it appears you are
notified, and opening the review window:
- Connects via BLE and downloads the notes held in offline storage
- Clears each note from the device as it is read, keeping the raw data on this Mac
- Lets you pick which notes to process
- Renders the selected strokes as black-on-white PNGs
- Transcribes them with a local Ollama model and files the result in your vault

## Tech Stack

- **Language:** Python 3.x
- **BLE Communication:** `bleak` (asyncio-based BLE library)
- **Image Rendering:** `Pillow` for stroke-to-PNG conversion
- **OCR:** Apple Vision (via PyObjC) reads the header line that routes each note
- **AI Integration:** local Ollama models over HTTP, configured in Preferences

## Architecture

The service operates in four logical stages:

1. **Watcher** — Background BLE poller that notifies when the Slate appears
2. **Sync** — GATT connection establishment and data download from Offline Storage characteristic
3. **Render** — Decode WILL 2.0 binary format (X, Y, Pressure arrays) into black-on-white PNG images
4. **Ingest** — Send PNG to the configured AI handler for transcription

After successful download, the service sends a 'Clear Memory' ACK command to the Slate to free up device storage.

## Protocol Details

- **BLE UART Service UUID:** `6e400001-b5a3-f393-e0a9-e50e24dcca9e`
- **Data Format:** WILL 2.0 (binary coordinate streams)
- **Connection:**
  - Initial bonding requires manual pairing (hold device button for 6 seconds)
  - Subsequent connections are automatic via stored MAC address
- **Reference Implementation:** The [`tuhi` project](https://github.com/libratbag/tuhi) provides handshake logic and coordinate reconstruction for Wacom Smartpads

## Installation

```bash
# Clone the repository
git clone https://github.com/karner/BambooSync.git
cd BambooSync

# Install dependencies
pip install -r requirements.txt
```

## Pairing

The Slate only accepts a Mac it has been registered with. To pair from the app:

1. Launch the app and open **Preferences ▸ Device**
2. Click **Rescan** and select your Slate under *Nearby Devices*
3. Hold the Slate's button until it flashes (pairing mode)
4. Click **Pair**, then press the Slate's button once when prompted

The paired device becomes the configured one and is remembered in Preferences.
Re-pair the same way if syncing ever reports that this Mac is not registered.

The `[device]` block in `config.toml` seeds Preferences on first launch only —
after that the device is managed in Preferences and edits to `config.toml` have
no effect. `register.py` does the same registration from the terminal and is kept
only as a fallback.

## Configuration

Everything user-facing lives in **Preferences**, opened from the menu bar icon:

- **Vaults** — name → path. Names become `VAULT_<NAME>_PATH` environment variables.
- **Device** — which Slate to sync with, and pairing.
- **Handlers** — Ollama endpoints and models used for transcription, and which is the default.
- **Sync** — whether to watch for the Slate, where the scratch folder lives, and what
  happens to notes that cannot be filed.

`config.toml` holds the protocol constants (service and characteristic UUIDs, opcodes)
plus the `[device]` and `[host]` values that seed Preferences on first launch.

`workflow.json` defines the document types — the stages, required fields and prompt for
each kind of note. Its `_readme` key documents the format.

## Usage

```bash
python main.py                    # menu bar app
python sync.py                    # one-shot sync from the terminal
python tools/ingest.py note.png   # run a PNG through the pipeline, no BLE
```

With *Notify me when the Slate is nearby* enabled, the app watches for your device and
notifies you when it appears. Clicking the notification opens the review window, which
downloads what is stored and lets you choose which notes to run through transcription.

Syncing removes pages from the Slate: each note is deleted from the device as it is read,
because that is the only way to reach the next one. Anything you do not import is kept on
this Mac in `spool/` inside the scratch folder.

## Development

### Project Structure

- `app/` — The application: `client/` (menu bar, windows), `business_logic/`
  (managers, engines), `resource_access/` (BLE, vault), `utilities/`
- `tools/ingest.py` — Runs a PNG through OCR/transcription without a device
- `main.py` — Entry point and service orchestration
- `discover.py` — BLE device discovery
- `download.py` — Data download from device
- `parse.py` — WILL 2.0 format parser
- `sync.py` — Synchronization logic
- `register.py` — Standalone device registration (superseded by Preferences ▸ Device ▸ Pair)

## Requirements

- macOS (Bluetooth LE support)
- Python 3.11+ (`tomllib`)
- Wacom Bamboo Slate device
- An Ollama instance for transcription (configured in Preferences ▸ Handlers)

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

This project uses the following open-source libraries:
- [bleak](https://github.com/hbldh/bleak) - MIT License (BLE communication)
- [Pillow](https://github.com/python-pillow/Pillow) - HPND License (image processing)
- [rumps](https://github.com/jaredks/rumps) - MIT License (macOS status bar)
- [PyYAML](https://github.com/yaml/pyyaml) - MIT License (configuration)
- [PyObjC](https://github.com/ronaldoussoren/pyobjc) - MIT License (macOS frameworks)

Special thanks to:
- [tuhi project](https://github.com/libratbag/tuhi) for Wacom protocol reference
- Wacom for the Bamboo Slate hardware
