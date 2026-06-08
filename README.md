# cthrobt — Nintendo Gamepad Controller (PC side)

> [中文说明](README.zh-CN.md)

PC-side Python suite that reads a Nintendo Switch Pro Controller and streams gamepad state to an STM32 board (real hardware or Renode simulation) over TCP.

## Architecture

```
┌─────────────────────────────────────────────┐
│               cthrobt (PC side)             │
│                                             │
│  controller.py ──TCP JSON──► bridge.py      │
│     (gamepad / mock)          (STM32 side)  │
│                                             │
│  simulator.py ◄──TCP JSON── controller.py  │
│     (debug only, no Renode)                 │
│                                             │
│  compare.py                                 │
│     sent log ──► diff ──► test_report.md    │
└─────────────────────────────────────────────┘
```

### Files

| File | Role |
|------|------|
| `controller.py` | Reads Nintendo gamepad via pygame, sends JSON over TCP. Supports `--mock` for no-hardware testing |
| `simulator.py` | Standalone TCP server — receives packets and prints them. Debug alternative to Renode |
| `compare.py` | Compares sent JSONL log vs STM32 UART3 output, generates Markdown test report |
| `config.ini` | All runtime config: host/port, protocol, deadzone, button/axis mapping |

## Communication Protocol

### JSON format (default)
```json
{"buttons":{"A":true,"B":false,...},"axes":{"LX":0.5,"LY":0.0,"RX":-0.3,"RY":0.0},"hat":[0,1]}
```
Sent as newline-delimited ASCII over TCP.

### Binary format (14 bytes, optional)
```
[0xAA][uint16 btn_mask][int8 hat_x][int8 hat_y][int16 LX][int16 LY][int16 RX][int16 RY][XOR checksum]
```
Select via `protocol = binary` in `config.ini`.

## Quick Start

### Requirements
- Python 3.9+
- `pip install -r requirements.txt` (pygame-ce for Python 3.14+)

### Setup
```bash
# macOS / Linux
bash scripts/setup.sh

# Windows
scripts\setup.bat
```

### Run with real hardware
```bash
# Terminal 1 (STM32 side) — start bridge.py or flash to real board
# Terminal 2
python controller.py                  # real gamepad
python controller.py --config my.ini  # custom config
```

### Mock mode (no gamepad needed)
```bash
# macOS / Linux
bash scripts/run_mock.sh [count] [interval_sec]

# Windows
scripts\run_mock.bat [count] [interval_sec]
```
Default: 20 packets, 0.5 s interval.  
Sent packets are logged to `logs/mock_sent_<timestamp>.jsonl`.

### Standalone debug (no STM32/Renode)
```bash
# Terminal 1
bash scripts/run_simulator.sh   # or scripts\run_simulator.bat

# Terminal 2
bash scripts/run_mock.sh
```

### Generate test report
```bash
bash scripts/compare.sh         # macOS / Linux
scripts\compare.bat             # Windows
```
Report saved to `logs/test_report_<timestamp>.md`.

## Configuration (`config.ini`)

| Section | Key | Default | Description |
|---------|-----|---------|-------------|
| `[network]` | `host` | `127.0.0.1` | Target IP (STM32 or simulator) |
| `[network]` | `port` | `7777` | Target port |
| `[network]` | `protocol` | `json` | `json` or `binary` |
| `[network]` | `only_on_change` | `true` | Send only when state changes |
| `[gamepad]` | `deadzone` | `0.05` | Analog stick deadzone (0–1) |
| `[gamepad]` | `poll_hz` | `100` | Gamepad polling frequency |

## Button Mapping (Nintendo Switch Pro Controller)

| Index | Name | Index | Name |
|-------|------|-------|------|
| 0 | B | 8 | MINUS |
| 1 | A | 9 | PLUS |
| 2 | Y | 10 | L_STICK |
| 3 | X | 11 | R_STICK |
| 4 | L | 12 | HOME |
| 5 | R | 13 | CAPTURE |
| 6 | ZL | — | — |
| 7 | ZR | — | — |

Axes: `LX`, `LY`, `RX`, `RY` (−1.0 to +1.0)  
Hat: `[x, y]` where x ∈ {−1, 0, +1}, y ∈ {−1, 0, +1}

## Scripts Reference

All scripts are in the `scripts/` directory. Each has a `.bat` (Windows) and `.sh` (macOS/Linux) version.

| Script | Windows | macOS/Linux | Description |
|--------|---------|-------------|-------------|
| **setup** | `scripts\setup.bat` | `bash scripts/setup.sh` | Install Python dependencies (`pip install -r requirements.txt`). Run once after cloning or when switching Python versions. |
| **run_controller** | `scripts\run_controller.bat` | `bash scripts/run_controller.sh` | **Normal operation.** Connect a real Nintendo gamepad and stream input to STM32 (real board or Renode simulation). Reads target host/port from `config.ini`. Reconnects automatically on disconnect. |
| **run_mock** | `scripts\run_mock.bat [count] [interval]` | `bash scripts/run_mock.sh [count] [interval]` | Send random gamepad packets without a real controller (for testing/verification). Default: 20 packets, 0.5 s interval. Saves sent log to `logs/mock_sent_<ts>.jsonl`. |
| **run_simulator** | `scripts\run_simulator.bat` | `bash scripts/run_simulator.sh` | Start standalone debug simulator on port 7777. Use this instead of bridge.py when you want to test controller.py without Renode or real hardware. **Do not run at the same time as bridge.py.** |
| **compare** | `scripts\compare.bat` | `bash scripts/compare.sh` | Compare the latest `logs/mock_sent_*.jsonl` against `../cthrobt_stm/received_signals.txt` and generate a Markdown test report in `logs/test_report_<ts>.md`. Run after mock finishes and bridge.py reports "Log is ready". |

### Typical workflows

**Normal operation (real gamepad → STM32 / Renode):**
```
[Terminal 1 — cthrobt_stm]          [Terminal 2 — cthrobt]
scripts\run_simulation.bat    →      (wait for "Waiting for controller.py")
                                     scripts\run_controller.bat
```

**Communication test (no gamepad needed):**
```
[Terminal 1 — cthrobt_stm]          [Terminal 2 — cthrobt]
scripts\run_simulation.bat    →      (wait for "Waiting for controller.py")
                                     scripts\run_mock.bat
(wait for "Log is ready")     →      scripts\compare.bat
                                     open logs\test_report_*.md
```

**Debug without STM32/Renode:**
```
[Terminal 1 — cthrobt]              [Terminal 2 — cthrobt]
scripts\run_simulator.bat     →      scripts\run_controller.bat
                                     (or scripts\run_mock.bat)
```

## Logs

| File | Created by | Contents |
|------|-----------|---------|
| `logs/ctrl_<ts>.log` | `controller.py` | Full session log |
| `logs/mock_sent_<ts>.jsonl` | `controller.py --mock` | One JSON state per line |
| `logs/test_report_<ts>.md` | `compare.py` | Pass/fail comparison report |
