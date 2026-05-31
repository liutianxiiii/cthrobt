#!/usr/bin/env python3
"""
STM32 Simulator — TCP server that receives gamepad packets from controller.py
and prints them to the console.

Supports both JSON and binary protocols (auto-detected from first byte).

Usage:
    python simulator.py [--config config.ini]
"""
from __future__ import annotations

import os
import sys
import struct
import json
import socket
import logging
import argparse
import configparser
import threading
from datetime import datetime

BINARY_PKT_LEN = 14   # total bytes per binary packet
BINARY_START   = 0xAA

BUTTON_NAMES: dict = {
    0:  "B",       1:  "A",       2:  "Y",       3:  "X",
    4:  "L",       5:  "R",       6:  "ZL",      7:  "ZR",
    8:  "MINUS",   9:  "PLUS",   10: "L_STICK", 11: "R_STICK",
    12: "HOME",   13: "CAPTURE",
}

HAT_LABELS: dict = {
    ( 0,  1): "UP",       ( 0, -1): "DOWN",
    (-1,  0): "LEFT",     ( 1,  0): "RIGHT",
    ( 1,  1): "UP-RIGHT", (-1,  1): "UP-LEFT",
    ( 1, -1): "DN-RIGHT", (-1, -1): "DN-LEFT",
}


def setup_logging() -> logging.Logger:
    logger = logging.getLogger("stm32-sim")
    logger.setLevel(logging.DEBUG)
    fmt = logging.Formatter("%(asctime)s.%(msecs)03d  %(message)s", datefmt="%H:%M:%S")
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    logger.addHandler(ch)
    return logger


# ── Protocol helpers ──────────────────────────────────────────────────────

def parse_binary(data: bytes) -> "dict | None":
    """
    Decode a 14-byte binary packet.
    Returns None on bad start-byte or checksum mismatch.
    """
    if len(data) != BINARY_PKT_LEN or data[0] != BINARY_START:
        return None

    expected_chk = 0
    for b in data[:13]:
        expected_chk ^= b
    if expected_chk != data[13]:
        return None

    _, btn_mask, hat_x, hat_y, lx, ly, rx, ry = struct.unpack("<BHbbhhhh", data[:13])

    buttons = {
        BUTTON_NAMES.get(i, f"BTN{i}"): bool(btn_mask & (1 << i))
        for i in range(16)
    }
    axes = {
        "LX": round(lx / 32767, 4),
        "LY": round(ly / 32767, 4),
        "RX": round(rx / 32767, 4),
        "RY": round(ry / 32767, 4),
    }
    return {"buttons": buttons, "axes": axes, "hat": [hat_x, hat_y]}


def format_state(state: dict) -> str:
    """Pretty-print an active gamepad state."""
    parts = [name for name, v in state.get("buttons", {}).items() if v]
    parts += [f"{n}={v:+.3f}" for n, v in state.get("axes", {}).items() if v != 0.0]
    hat = state.get("hat", [0, 0])
    if hat and hat != [0, 0]:
        label = HAT_LABELS.get(tuple(hat), str(hat))
        parts.append(f"HAT:{label}")
    return "  ".join(parts) if parts else "(idle)"


def recv_exactly(sock: socket.socket, n: int) -> bytes:
    """Read exactly n bytes, raising ConnectionError on EOF."""
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("Remote side closed the connection")
        buf += chunk
    return buf


# ── Per-client handler ────────────────────────────────────────────────────

def handle_binary(conn: socket.socket, first_byte: bytes, log: logging.Logger):
    """Receive and decode binary packets until disconnect."""
    log.info("[~] Protocol: BINARY (14-byte packets with XOR checksum)")
    buf = first_byte  # already have 0xAA

    while True:
        buf += recv_exactly(conn, BINARY_PKT_LEN - len(buf))
        state = parse_binary(buf)

        if state:
            log.info(f"[RX-BIN] {format_state(state)}")
            buf = b""
        else:
            log.warning(f"[!] Checksum error — raw: {buf.hex()}  (resyncing…)")
            buf = b""
            # seek next start byte
            while True:
                b = recv_exactly(conn, 1)
                if b == bytes([BINARY_START]):
                    buf = b
                    break


def handle_json(conn: socket.socket, first_byte: bytes, log: logging.Logger):
    """Receive and decode newline-delimited JSON packets until disconnect."""
    log.info("[~] Protocol: JSON (newline-delimited)")
    text_buf = first_byte.decode("ascii", errors="replace")

    while True:
        chunk = conn.recv(4096)
        if not chunk:
            raise ConnectionError("Remote side closed the connection")
        text_buf += chunk.decode("ascii", errors="replace")

        while "\n" in text_buf:
            line, text_buf = text_buf.split("\n", 1)
            line = line.strip()
            if not line:
                continue
            try:
                state = json.loads(line)
                log.info(f"[RX-JSON] {format_state(state)}")
            except json.JSONDecodeError as e:
                log.warning(f"[!] JSON error: {e} — raw: {line!r}")


def handle_client(conn: socket.socket, addr: tuple, log: logging.Logger):
    peer = f"{addr[0]}:{addr[1]}"
    log.info(f"[+] Controller connected from {peer}")
    try:
        first = recv_exactly(conn, 1)  # peek at first byte to detect protocol
        if first == bytes([BINARY_START]):
            handle_binary(conn, first, log)
        else:
            handle_json(conn, first, log)
    except ConnectionError as e:
        log.info(f"[-] {peer} disconnected ({e})")
    except Exception as e:
        log.error(f"[!] Unexpected error from {peer}: {e}")
    finally:
        try:
            conn.close()
        except OSError:
            pass
        log.info(f"[ ] Connection from {peer} closed\n")


# ── Server ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="STM32 Simulator — gamepad packet receiver")
    parser.add_argument("--config", default="config.ini", help="Path to config file")
    args = parser.parse_args()

    cfg_path = args.config
    if not os.path.isabs(cfg_path):
        cfg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), cfg_path)

    cfg = configparser.ConfigParser()
    cfg.read(cfg_path, encoding="utf-8")

    host = cfg.get   ("simulator", "host", fallback="127.0.0.1")
    port = cfg.getint("simulator", "port", fallback=9000)

    log = setup_logging()
    log.info("=" * 50)
    log.info("  STM32 Simulator")
    log.info("=" * 50)
    log.info(f"Listening on  {host}:{port}")
    log.info("Accepts both JSON and binary protocols (auto-detected)")
    log.info("Waiting for controller … Ctrl+C to quit\n")

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    try:
        server.bind((host, port))
    except OSError as e:
        log.error(f"Cannot bind to {host}:{port}: {e}")
        sys.exit(1)

    server.listen(5)

    try:
        while True:
            conn, addr = server.accept()
            t = threading.Thread(
                target=handle_client, args=(conn, addr, log), daemon=True
            )
            t.start()
    except KeyboardInterrupt:
        log.info("\nShutting down simulator.")
    finally:
        server.close()


if __name__ == "__main__":
    main()
