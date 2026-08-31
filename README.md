# Bamboo Slate Sync

> **⚠️ PRE-ALPHA / WORK IN PROGRESS**  
> This project is in active development and not yet ready for production use. Features may be incomplete, APIs may change, and bugs are expected. Use at your own risk.

A macOS background service that automatically detects a Wacom Bamboo Slate via Bluetooth Low Energy (BLE), downloads stored handwritten notes, renders them as images, and sends them to an AI for transcription and summarization.

## Overview

This service runs in the background and monitors for your Wacom Bamboo Slate device. When detected, it automatically:
- Connects via BLE
- Downloads handwritten notes from offline storage
- Renders strokes as high-quality PNG images
- Transcribes content using AI (Google Generative AI or OpenAI)
- Clears the device memory after successful download

## Tech Stack

- **Language:** Python 3.x
- **BLE Communication:** `bleak` (asyncio-based BLE library)
- **Image Rendering:** `Pillow` or `matplotlib` for stroke-to-PNG conversion
- **AI Integration:** `google-generativeai` or `openai` SDK for image-to-text processing

## Architecture

The service operates in four logical stages:

1. **Watcher** — Background BLE scanner monitoring for the Slate's UUID
2. **Sync** — GATT connection establishment and data download from Offline Storage characteristic
3. **Render** — Decode WILL 2.0 binary format (X, Y, Pressure arrays) into black-on-white PNG images
4. **Ingest** — POST PNG to AI API for transcription and summarization

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

Create a `config.toml` file with your AI API credentials:

```toml
# Example configuration
[ai]
provider = "openai"  # or "google"
api_key = "your-api-key-here"

[ble]
device_name = "Bamboo Slate"
```

## Usage

```bash
# Run the service
python main.py
```

The service will run in the background, automatically detecting and syncing your Bamboo Slate when in range.

## Development

### Project Structure

- `main.py` — Entry point and service orchestration
- `discover.py` — BLE device discovery
- `download.py` — Data download from device
- `parse.py` — WILL 2.0 format parser
- `sync.py` — Synchronization logic
- `register.py` — Standalone device registration (superseded by Preferences ▸ Device ▸ Pair)

## Requirements

- macOS (Bluetooth LE support)
- Python 3.8+
- Wacom Bamboo Slate device
- Active AI API key (OpenAI or Google)

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
