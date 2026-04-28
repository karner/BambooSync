# Project: Wacom Slate Zero-Touch AI Ingest

## 1. Overview
The goal is to create a background service for macOS that automatically detects a Wacom Bamboo Slate via Bluetooth Low Energy (BLE), downloads stored handwritten notes, renders them as images, and sends them to an AI for processing.

---

## 2. Technical Specifications

### Hardware Communication
* **Protocol:** Bluetooth Low Energy (BLE) / GATT.
* **Discovery:** Manual trigger (hold button for 6s) for initial bonding; the script should then "watch" for the specific MAC address.
* **Primary Library:** `bleak` (Python).

### Data Format (The WILL Challenge)
* **Raw Data:** The Slate stores data in **WILL 2.0** (binary coordinate streams).
* **Parsing:** You must convert raw bytes into X, Y, and Pressure arrays.
* **Rendering:** Use `Pillow` or `matplotlib` to draw the strokes onto a 2D canvas (PNG/JPG).

---

## 3. The Workflow Logic (The "Listener")

| Phase | Action | Detail |
| :--- | :--- | :--- |
| **Watcher** | Scan | Script runs in the background scanning for the Slate's BLE UUID. |
| **Sync** | Connection | Automatically connect when the device is turned on. |
| **Download**| Transfer | Request chunks from the "Offline Storage" GATT characteristic. |
| **Clear** | ACK | Send the 'Clear Memory' command to the Slate after a successful save. |
| **Render** | Transform | Convert coordinates to a high-contrast black-on-white PNG. |
| **Ingest** | AI API | POST the PNG to Gemini/OpenAI for transcription or summarization. |

---

## 4. Required GATT Info (Reverse Engineering Base)
To build this, the following references are critical:
* **Wacom UART Service:** `6e400001-b5a3-f393-e0a9-e50e24dcca9e`
* **Reference Code:** Research the **`tuhi`** project (libratbag/tuhi) on GitHub. It contains the logic for the "handshake" and coordinate reconstruction for Wacom Smartpads.

---

## 5. Development Steps for Claude Code
1.  **Scanner Script:** Create a Python script using `bleak` to identify the Slate's UUID and MAC address.
2.  **Data Pull:** Implement the GATT notification listener to receive the binary stream when the button is pressed/synced.
3.  **Parsing Engine:** Build a function to decode the WILL 2.0 byte packets.
4.  **AI Pipeline:** Integrate the `google-generativeai` or `openai` Python SDK to handle the final image-to-text conversion.
