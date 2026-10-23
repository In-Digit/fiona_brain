# Fiona Brain 🧠🚗

**The central computational and telemetry hub for the "Soul of Fiona" ecosystem.**

Fiona Brain is a Linux-based microservice system that replaces traditional car head units. It acts as the central aggregator for vehicle telemetry, virtual fuel tank calculations, and network distribution.

---

## 🌟 Overview

This project is the "brain" of a custom automotive system built for a 2001 Ford Focus (Fiona). It runs on a portable Linux computer, communicating with the car's ECU via Bluetooth (ELM327) and with peripheral ESP32/ESP8266 modules via a custom UDP protocol.

- **OBD-II Telemetry:** Reads real-time data (RPM, Speed, MAF, etc.) and applies 3-point smoothing.
- **Virtual Fuel Tank:** Calculates fuel consumption using MAF, STFT, and LTFT. Features "Zenon's paradox" progressive calibration and multi-fuel presets.
- **Fiona-Net UDP Protocol:** Aggregates data from peripheral modules and broadcasts a unified data stream (8-byte bitmask + CRC8).
- **Web Dashboard:** Serves a responsive HTML/JS interface (Port 8000) for mobile devices.
- **LIVI Integration:** Bridges telemetry into Android Auto (Socket.IO Port 4000).
- **Emulation Mode:** Allows full system testing without physical hardware.

---

## 📁 Project Structure

```text
fiona_brain/
├── main.py                 # Entry point
├── config.py               # Constants and settings
├── fb.sh                   # Bash launcher script
├── data/                   # JSON storage (state, presets)
├── web/                    # HTML/JS dashboard
├── core/                   # State management, Engine, Protocol
├── hardware/               # ELM327, Parser, Emulator
├── services/               # Fuel, UDP, Web, Storage, Telemetry
└── utils/                  # CRC8, Helpers