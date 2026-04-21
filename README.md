# VW Atlas 2018 — CAN / OBD-II diagnostics

This project talks to the car over **raw CAN** using [python-can](https://github.com/hardbyte/python-can) and **ISO-TP** (ISO 15765) via [can-isotp](https://github.com/pylessard/python-can-isotp). It does **not** use a serial ELM327 command set or the `obd` PyPI package.

**Stack:** OBD-II services 0x03/0x07/0x01 (DTCs and live data) and UDS `0x22` read-by-identifier (e.g. LPFP duty) on the same ISO-TP session the factory tools use, once the CAN link is up.

## Hardware

Many “USB–CAN” adapters are **not** a `/dev/ttyUSB*` line with OBD text; the kernel or `slcand` exposes a **SocketCAN** interface (often `can0`) or a **slcan** serial device you pass to `python-can`.

| Amazon ASIN | Notes |
|---|---|
| B081N7G2BR | Check the listing: if it is a true CAN interface, use the sections below. If it is an ELM327, you would use a different tool, not this repo. |
| B09K3LL93Q | Cables and adapters; same as long as the PC ends up with a working CAN bus. |

Find what Linux created after plugging in:

```bash
ip link
dmesg | tail -30
# Often: can0 (SocketCAN) or /dev/ttyACMx, /dev/ttyUSB* for SLCAN
```

### SocketCAN (typical: native USB–CAN, or `slcand` already bound)

Bring the bus up (500 kbit/s is the usual OBD / gateway line on VAG; confirm with your hardware docs):

```bash
sudo ip link set can0 up type can bitrate 500000
```

Then run:

```bash
uv run dump-codes   --can-interface socketcan --can-channel can0
uv run fuel-monitor --can-interface socketcan --can-channel can0
```

### SLCAN (serial “ASCII CAN” to a TTY)

Use the TTY as the `python-can` channel, for example:

```bash
uv run dump-codes --can-interface slcan --can-channel /dev/ttyACM0 --slcan-baud 115200
```

Serial baud and wiring must match the adapter’s manual (115200, 1 Mbaud, etc.).

## Permissions and groups

```bash
# Serial devices:
sudo usermod -aG dialout $USER
# Or for SocketCAN, your distro may add you to a group, or you run with appropriate rights.
```

## Project setup (uv)

```bash
uv sync
```

If your environment’s default PyPI index is a private one that fails, use a clean index for this project (example):

```bash
UV_NO_CONFIG=1 uv sync
```

## Commands (entry points)

### `dump-codes`

Stored DTCs (0x03), pending DTCs (0x07), and a short MIL / DTC count read from mode 0x01 PID 0x01.

```bash
uv run dump-codes --can-channel can0
```

### `fuel-monitor`

Standard mode 0x01 PIDs (load, RPM, fuel rail, trims) plus UDS DIDs `0xC006` (LPFP duty) and `0x1173` (HPFP target) when the ECU returns them on `0x7E0`/`0x7E8`.

```bash
uv run fuel-monitor --can-channel can0
uv run fuel-monitor --can-channel can0 --once
```

**IDs:** defaults are VAG OBD “engine” addresses `0x7E0` → `0x7E8`. If the ECU is silent, try your scan-tool / wiring notes with `--tx-id` / `--rx-id`.

## Interpreting LPFP duty (warm idle, engine running)

| Duty | Interpretation (rule of thumb) |
|---|---|
| < 50% | Healthy headroom |
| 50–70% | Keep fuel level up; re-check after fill |
| 70–85% | Likely degraded or low tank |
| > 85% | High demand; service may be near |

## P0087 in context

P0087 = fuel rail or system pressure too low. A weak **LPFP** in the tank can leave the **HPFP** without enough low-pressure supply; the ECU will show large positive fuel trims in some conditions. DIDs and scaling are calibration-specific; this tool’s LPFP line follows common VAG mappings but may be “no response” if the ECU or calibration does not publish that identifier on the addressed ECU.
