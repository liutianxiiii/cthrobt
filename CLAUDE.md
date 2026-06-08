# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

PC-side Python suite (`cthrobt`) that reads a Nintendo Switch Pro Controller (via pygame) and streams its
button/axis/hat state as JSON or binary packets over TCP to an STM32 board — either real hardware, a
Renode-simulated board (in the sibling `cthrobt_stm` repo, via its `bridge.py`), or this repo's own
standalone debug simulator. There is no automated test suite; verification is done by sending known mock
packets and diffing the STM32's reported output against what was sent.

## Setup & commonly used commands

No build step — this is a small set of standalone Python scripts.

```bash
# Install deps (pygame>=2.0.0; use pygame-ce on Python 3.14+ where pygame has no wheel)
scripts\setup.bat            # Windows
bash scripts/setup.sh        # macOS/Linux

# Normal operation: real gamepad -> STM32 / Renode (reads target host:port from config.ini)
python controller.py [--config my.ini]

# Mock mode: send N random packets without a real controller (default 20 @ 0.5s)
# Logs sent packets to logs/mock_sent_<ts>.jsonl
python controller.py --mock [--mock-count N] [--mock-interval SEC] [--mock-log FILE]
scripts\run_mock.bat [count] [interval]      # Windows
bash scripts/run_mock.sh [count] [interval]  # macOS/Linux

# Standalone debug TCP server (use INSTEAD of cthrobt_stm's bridge.py — never run both,
# they share port 7777). Auto-detects JSON vs binary protocol per connection.
python simulator.py [--config config.ini]
scripts\run_simulator.bat / bash scripts/run_simulator.sh

# Generate a pass/fail Markdown report comparing a sent JSONL log against the STM32's
# received-signal log (default ../cthrobt_stm/received_signals.txt) -> logs/test_report_<ts>.md
python compare.py --sent logs/mock_sent_<ts>.jsonl [--received PATH] [--output FILE]
scripts\compare.bat / bash scripts/compare.sh   # auto-picks the latest mock_sent_*.jsonl
```

There is no linter or formal test command configured; treat a clean mock-mode run plus a 100% `compare.py`
report as the correctness check for protocol-level changes.

### End-to-end verification workflow

1. Start the receiver first: either `cthrobt_stm`'s `scripts\run_simulation.bat` (Renode + bridge.py,
   wait for "Waiting for controller.py") or this repo's `run_simulator` (debug, no Renode).
2. Run `run_mock` (or `run_controller` with a real gamepad) in a second terminal.
3. Once the receiver reports it's done ("Log is ready" for bridge.py), run `compare` and inspect
   `logs/test_report_*.md`.

## Architecture

```
controller.py ──TCP (JSON or binary, newline/length-framed)──► STM32 / bridge.py / simulator.py
     │
     └── logs/mock_sent_<ts>.jsonl  (only in --mock mode)
                                                              │
compare.py  ◄── diffs sent JSONL against the receiver's "[CTRL] ..." log lines ──┘
     └── logs/test_report_<ts>.md
```

- **`controller.py`** — `GamepadController` class does everything: reads `config.ini`, opens the gamepad
  via pygame, polls/encodes/sends state over a TCP socket, auto-reconnects, and logs to both console and
  `logs/ctrl_<ts>.log`. `--mock` mode bypasses the gamepad and feeds `_mock_state()`-generated random
  states through the same `send()`/encoding path, recording every packet sent to a JSONL log so it can
  later be diffed against what the STM32 says it received.
- **`simulator.py`** — minimal multi-threaded TCP server that stands in for the STM32 (or its Renode
  bridge) during debugging. Peeks at the first byte of each connection to auto-detect JSON vs. binary,
  then decodes and pretty-prints packets. Cannot run alongside `cthrobt_stm`'s `bridge.py` (port clash).
- **`compare.py`** — reconstructs the *expected* `[CTRL] ...` string for each sent state
  (`expected_ctrl()`), pulls the *actual* `[CTRL] ...` lines the STM32 reported back
  (`load_received()`, filtered by the `_GAMEPAD_LINE` regex to skip startup noise), normalizes both
  (`_normalize()` — token sets with floats rounded to 3 decimals so formatting differences don't cause
  false mismatches), and emits a row-by-row Markdown report with a pass percentage.
- **`config.ini`** — single source of truth for runtime behavior (Chinese-language comments): network
  target/protocol/timing under `[network]`, gamepad deadzone/poll rate/name filter under `[gamepad]`,
  log directory under `[logging]`, and optional button/axis index→name overrides under `[button_map]`
  / `[axis_map]` (needed because SDL2 joystick indices vary by OS/driver — the running program prints
  the detected device name and indices to help calibrate these).

### Wire protocol (must stay in sync across `controller.py`, `simulator.py`, and the STM32/Renode side)

- **JSON** (default): `{"buttons":{...},"axes":{"LX":..,"LY":..,"RX":..,"RY":..},"hat":[x,y]}\n`,
  newline-delimited ASCII.
- **Binary** (opt-in via `protocol = binary`): fixed 14-byte little-endian packet —
  `0xAA, uint16 button_mask, int8 hat_x, int8 hat_y, int16 LX/LY/RX/RY, uint8 XOR-checksum`. See the
  docstring on `GamepadController._encode_binary` for the exact byte layout. **Note:** the STM32 side
  currently only implements JSON parsing — binary mode is untested end-to-end (see DEVELOPMENT_NOTES.md).
- Default Nintendo Switch Pro Controller index→name maps for buttons/axes live in both `controller.py`
  (`DEFAULT_BUTTON_NAMES`/`DEFAULT_AXIS_NAMES`) and `simulator.py` (`BUTTON_NAMES`) and must be kept
  consistent; `config.ini`'s `[button_map]`/`[axis_map]` can override per-machine if SDL2 reports
  different indices.

### Relationship to `cthrobt_stm`

This repo only covers the PC side. The STM32/Renode side (bridge.py, `received_signals.txt`,
`run_simulation.bat`) lives in a sibling repo `../cthrobt_stm`, which `compare.py` reads from by
default. Expect to coordinate changes to the wire protocol or `[CTRL]` log format with that repo.

## Known gotchas (from DEVELOPMENT_NOTES.md)

- On Python 3.14+, install `pygame-ce` instead of `pygame` (no official wheel yet); it's a drop-in
  replacement (`import pygame` still works).
- Renode processes UART output slower than real-time — `bridge.py` waits for output to go quiet (5s)
  before signaling it's ready for `compare.py`; don't run `compare.py` too early or sent/received counts
  will mismatch.
- `simulator.py` and `bridge.py` both bind port 7777 — never run them simultaneously.
