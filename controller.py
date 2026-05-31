#!/usr/bin/env python3
"""
Nintendo Gamepad → STM32 Socket Controller

Reads input from a Nintendo-compatible gamepad and streams button/axis state
to a remote STM32 board over a TCP socket.

Usage:
    python controller.py [--config config.ini]
"""
from __future__ import annotations

import os
import sys
import struct
import time
import json
import socket
import logging
import argparse
import configparser
from datetime import datetime
from pathlib import Path

try:
    import pygame
except ImportError:
    print("pygame is not installed. Run:  pip install pygame")
    sys.exit(1)


# ── Default Nintendo Switch Pro Controller button map ─────────────────────
# Button indices come from SDL2 raw joystick API (no GC remapping).
# If your controller reports different indices, override in config.ini
# under [button_map].
DEFAULT_BUTTON_NAMES: dict = {
    0:  "B",
    1:  "A",
    2:  "Y",
    3:  "X",
    4:  "L",
    5:  "R",
    6:  "ZL",
    7:  "ZR",
    8:  "MINUS",
    9:  "PLUS",
    10: "L_STICK",
    11: "R_STICK",
    12: "HOME",
    13: "CAPTURE",
}

DEFAULT_AXIS_NAMES: dict = {
    0: "LX",
    1: "LY",
    2: "RX",
    3: "RY",
}


# ── Logging setup ─────────────────────────────────────────────────────────

def setup_logging(log_dir: str) -> logging.Logger:
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = os.path.join(log_dir, f"ctrl_{ts}.log")

    logger = logging.getLogger("ctrl")
    logger.setLevel(logging.DEBUG)

    fmt = logging.Formatter("%(asctime)s.%(msecs)03d  %(message)s",
                            datefmt="%H:%M:%S")

    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    logger.info(f"Log file → {log_path}")
    return logger


# ── Main controller class ─────────────────────────────────────────────────

class GamepadController:

    def __init__(self, cfg: configparser.ConfigParser, log: logging.Logger):
        self.log = log

        # Network
        self.host            = cfg.get   ("network", "host",           fallback="192.168.1.100")
        self.port            = cfg.getint("network", "port",           fallback=8080)
        self.protocol        = cfg.get   ("network", "protocol",       fallback="json").lower()
        self.send_interval   = cfg.getfloat("network", "send_interval",fallback=0.05)
        self.only_on_change  = cfg.getboolean("network","only_on_change",fallback=True)
        self.reconnect_delay = cfg.getfloat("network", "reconnect_delay",fallback=3.0)

        # Gamepad
        self.deadzone    = cfg.getfloat("gamepad", "deadzone",      fallback=0.05)
        self.name_filter = cfg.get     ("gamepad", "name_contains",  fallback="").lower().strip()
        self.poll_hz     = cfg.getfloat("gamepad", "poll_hz",        fallback=100.0)

        # Button / axis name maps (with config overrides)
        self.btn_names  = dict(DEFAULT_BUTTON_NAMES)
        self.axis_names = dict(DEFAULT_AXIS_NAMES)

        if cfg.has_section("button_map"):
            for k, v in cfg.items("button_map"):
                try:
                    self.btn_names[int(k)] = v.upper()
                except ValueError:
                    pass
        if cfg.has_section("axis_map"):
            for k, v in cfg.items("axis_map"):
                try:
                    self.axis_names[int(k)] = v.upper()
                except ValueError:
                    pass

        # Reverse map for binary encoding
        self._name_to_idx: dict = {v: k for k, v in self.btn_names.items()}

        self.sock: "socket.socket | None" = None
        self.joystick = None
        self._last_state: "dict | None" = None

    # ── Socket ───────────────────────────────────────────────────────────

    def connect(self) -> bool:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.settimeout(5.0)
            s.connect((self.host, self.port))
            s.settimeout(None)
            s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self.sock = s
            self.log.info(f"[NET] Connected → {self.host}:{self.port}  protocol={self.protocol}")
            return True
        except OSError as e:
            self.log.error(f"[NET] Connection failed: {e}")
            try:
                s.close()
            except OSError:
                pass
            self.sock = None
            return False

    def disconnect(self):
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass
            self.sock = None
            self.log.info("[NET] Disconnected")

    def send(self, state: dict) -> bool:
        if not self.sock:
            return False
        try:
            data = (self._encode_json(state)
                    if self.protocol == "json"
                    else self._encode_binary(state))
            self.sock.sendall(data)
            return True
        except OSError as e:
            self.log.warning(f"[NET] Send error: {e}")
            self.disconnect()
            return False

    def _encode_json(self, state: dict) -> bytes:
        return (json.dumps(state, separators=(",", ":")) + "\n").encode("ascii")

    def _encode_binary(self, state: dict) -> bytes:
        """
        14-byte little-endian packet:
          [0]      0xAA             start marker
          [1-2]    uint16           button bitmask (bit N = button index N)
          [3]      int8             D-pad X  (-1 left / 0 / +1 right)
          [4]      int8             D-pad Y  (-1 down / 0 / +1 up)
          [5-6]    int16            left  stick X  (–32767 … +32767)
          [7-8]    int16            left  stick Y
          [9-10]   int16            right stick X
          [11-12]  int16            right stick Y
          [13]     uint8            XOR checksum of bytes [0..12]
        """
        btn_mask = 0
        for name, pressed in state["buttons"].items():
            if pressed:
                idx = self._name_to_idx.get(name)
                if idx is not None and idx < 16:
                    btn_mask |= (1 << idx)

        hat  = state.get("hat", [0, 0])
        axes = state.get("axes", {})

        def i16(v: float) -> int:
            return max(-32767, min(32767, int(v * 32767)))

        payload = struct.pack(
            "<BHbbhhhh",
            0xAA,
            btn_mask,
            hat[0], hat[1],
            i16(axes.get("LX", 0.0)),
            i16(axes.get("LY", 0.0)),
            i16(axes.get("RX", 0.0)),
            i16(axes.get("RY", 0.0)),
        )
        checksum = 0
        for b in payload:
            checksum ^= b
        return payload + bytes([checksum])

    # ── Gamepad ──────────────────────────────────────────────────────────

    def find_joystick(self) -> bool:
        count = pygame.joystick.get_count()
        if count == 0:
            self.log.warning("[JOY] No joysticks detected")
            return False

        self.log.info(f"[JOY] {count} joystick(s) found:")
        for i in range(count):
            j = pygame.joystick.Joystick(i)
            self.log.info(f"       [{i}] {j.get_name()!r}")

        chosen = None
        if self.name_filter:
            for i in range(count):
                j = pygame.joystick.Joystick(i)
                if self.name_filter in j.get_name().lower():
                    chosen = j
                    break
            if chosen is None:
                self.log.warning(
                    f"[JOY] No controller matched filter {self.name_filter!r} "
                    "— falling back to first device"
                )

        if chosen is None:
            chosen = pygame.joystick.Joystick(0)

        chosen.init()
        self.joystick = chosen
        self.log.info(
            f"[JOY] Active: {chosen.get_name()!r}  "
            f"buttons={chosen.get_numbuttons()}  "
            f"axes={chosen.get_numaxes()}  "
            f"hats={chosen.get_numhats()}"
        )
        return True

    def _apply_deadzone(self, v: float) -> float:
        return 0.0 if abs(v) < self.deadzone else round(v, 4)

    def read_state(self) -> dict:
        j = self.joystick
        buttons = {
            self.btn_names.get(i, f"BTN{i}"): bool(j.get_button(i))
            for i in range(j.get_numbuttons())
        }
        axes = {
            self.axis_names.get(i, f"AXIS{i}"): self._apply_deadzone(j.get_axis(i))
            for i in range(j.get_numaxes())
        }
        hat = list(j.get_hat(0)) if j.get_numhats() > 0 else [0, 0]
        return {"buttons": buttons, "axes": axes, "hat": hat}

    def _log_state(self, state: dict):
        HAT_NAMES = {
            ( 0,  1): "UP",        ( 0, -1): "DOWN",
            (-1,  0): "LEFT",      ( 1,  0): "RIGHT",
            ( 1,  1): "UP-RIGHT",  (-1,  1): "UP-LEFT",
            ( 1, -1): "DN-RIGHT",  (-1, -1): "DN-LEFT",
        }

        parts = [name for name, v in state["buttons"].items() if v]
        parts += [f"{n}={v:+.3f}" for n, v in state["axes"].items() if v != 0.0]

        hat = state["hat"]
        if hat != [0, 0]:
            label = HAT_NAMES.get(tuple(hat), str(hat))
            parts.append(f"HAT:{label}")

        if parts:
            self.log.info("[INPUT] " + "  ".join(parts))
        elif self._last_state is not None:
            prev_any = (
                any(self._last_state["buttons"].values()) or
                any(v != 0.0 for v in self._last_state["axes"].values()) or
                self._last_state["hat"] != [0, 0]
            )
            if prev_any:
                self.log.info("[INPUT] (released)")

    # ── Main loop ─────────────────────────────────────────────────────────

    def run(self):
        pygame.init()
        pygame.joystick.init()

        self.log.info("=" * 48)
        self.log.info("  Nintendo Gamepad → STM32 Controller")
        self.log.info("=" * 48)
        self.log.info(f"Target STM32 : {self.host}:{self.port}")
        self.log.info(f"Protocol     : {self.protocol}")
        self.log.info(f"Only-on-change: {self.only_on_change}")

        if not self.find_joystick():
            self.log.error("Aborting: no joystick found. Plug in the controller and retry.")
            pygame.quit()
            return

        self.log.info("Connecting to STM32 …")
        while not self.connect():
            self.log.info(f"Retry in {self.reconnect_delay:.0f}s …  (Ctrl+C to quit)")
            time.sleep(self.reconnect_delay)

        poll_sleep = 1.0 / self.poll_hz
        last_send_t = 0.0
        self.log.info("Controller running. Press Ctrl+C to exit.\n")

        try:
            while True:
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        return
                    if event.type == pygame.JOYDEVICEREMOVED:
                        self.log.warning("[JOY] Gamepad disconnected!")
                        self.joystick = None
                    if event.type == pygame.JOYDEVICEADDED and self.joystick is None:
                        self.log.info("[JOY] Gamepad reconnected — re-initialising …")
                        pygame.joystick.quit()
                        pygame.joystick.init()
                        self.find_joystick()

                if self.joystick is None:
                    time.sleep(1.0)
                    continue

                state = self.read_state()
                now   = time.monotonic()

                if self.only_on_change:
                    should_send = state != self._last_state
                else:
                    should_send = (now - last_send_t) >= self.send_interval

                if should_send:
                    self._log_state(state)
                    if not self.send(state):
                        self.log.info(f"[NET] Reconnecting in {self.reconnect_delay:.0f}s …")
                        time.sleep(self.reconnect_delay)
                        while not self.connect():
                            time.sleep(self.reconnect_delay)
                    self._last_state = state
                    last_send_t = now

                time.sleep(poll_sleep)

        except KeyboardInterrupt:
            self.log.info("\nInterrupted — shutting down.")
        finally:
            self.disconnect()
            pygame.quit()
            self.log.info("Done.")


# ── Entry point ───────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Nintendo Gamepad → STM32 Socket Controller"
    )
    parser.add_argument(
        "--config", default="config.ini",
        help="Path to config file (default: config.ini)"
    )
    args = parser.parse_args()

    cfg_path = args.config
    if not os.path.isabs(cfg_path):
        cfg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), cfg_path)

    cfg = configparser.ConfigParser()
    cfg.read(cfg_path, encoding="utf-8")

    log_dir = cfg.get("logging", "log_dir", fallback="logs")
    if not os.path.isabs(log_dir):
        log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), log_dir)

    logger = setup_logging(log_dir)

    if not os.path.exists(cfg_path):
        logger.warning(f"Config not found at {cfg_path!r} — using built-in defaults")
    else:
        logger.info(f"Config : {cfg_path}")

    GamepadController(cfg, logger).run()


if __name__ == "__main__":
    main()
