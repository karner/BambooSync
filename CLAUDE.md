# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

A macOS background service that auto-detects a Wacom Bamboo Slate via BLE, downloads stored handwritten notes, renders them as images, and sends them to an AI for transcription/summarization.

## Tech Stack

- **Language:** Python
- **BLE:** `bleak` (asyncio-based BLE library)
- **Rendering:** `Pillow` or `matplotlib` — strokes to black-on-white PNG
- **AI:** `google-generativeai` or `openai` SDK for image-to-text

## Architecture

The service has four logical stages:

1. **Watcher** — background BLE scanner watching for the Slate's UUID
2. **Sync** — GATT connection + download from the Offline Storage characteristic
3. **Render** — decode WILL 2.0 binary (X, Y, Pressure arrays) → PNG
4. **Ingest** — POST PNG to AI API for transcription

After a successful download, send the 'Clear Memory' ACK command to the Slate.

## Key Protocol Details

- **BLE UART Service UUID:** `6e400001-b5a3-f393-e0a9-e50e24dcca9e`
- **Data format:** WILL 2.0 (binary coordinate streams) — must be parsed into X/Y/Pressure arrays before rendering
- **Initial bonding:** Manual (hold button 6s); subsequent connections are automatic by MAC address
- **Reference implementation:** The [`tuhi` project](https://github.com/libratbag/tuhi) contains handshake logic and coordinate reconstruction for Wacom Smartpads — consult it when implementing the GATT layer
