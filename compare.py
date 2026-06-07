#!/usr/bin/env python3
"""
compare.py — Compare mock-sent packets with STM32 UART3 output and
             generate a Markdown test report.

Usage:
    python compare.py --sent logs/mock_sent_<ts>.jsonl
                      [--received ../cthrobt_stm/received_signals.txt]
                      [--output test_report.md]
"""
from __future__ import annotations

import json
import re
import argparse
import os
from datetime import datetime
from pathlib import Path

HAT_LABELS: dict = {
    (0,  1): "UP",       (0, -1): "DOWN",
    (-1, 0): "LEFT",     (1,  0): "RIGHT",
    (1,  1): "UP-RIGHT", (-1, 1): "UP-LEFT",
    (1, -1): "DN-RIGHT", (-1,-1): "DN-LEFT",
}


def expected_ctrl(state: dict) -> str:
    """Derive the expected [CTRL] output string from a sent state dict."""
    parts: list[str] = []

    for name, val in state["buttons"].items():
        if val:
            parts.append(name)

    for name, val in state["axes"].items():
        if val != 0.0:
            parts.append(f"{name}={val:+.3f}")

    hat = state.get("hat", [0, 0])
    if hat and hat != [0, 0]:
        label = HAT_LABELS.get(tuple(hat))  # type: ignore[arg-type]
        if label:
            parts.append(f"HAT:{label}")

    return " ".join(parts) if parts else "(idle)"


def _normalize(s: str) -> frozenset[str]:
    """Split into tokens, normalize axis float values, return as a set."""
    tokens: list[str] = []
    for t in s.split():
        if "=" in t:
            name, val = t.split("=", 1)
            try:
                tokens.append(f"{name}={float(val):+.3f}")
            except ValueError:
                tokens.append(t)
        else:
            tokens.append(t)
    return frozenset(tokens)


def load_sent(path: str) -> list[dict]:
    entries = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries


_GAMEPAD_LINE = re.compile(
    r'^(?:\(idle\)|'
    r'(?:[A-Z_]+=[-+]?\d+\.\d+\s*|HAT:\w+\s*|[A-Z_]+\s*)+'
    r')$'
)

def load_received(path: str) -> list[str]:
    """Extract gamepad-state lines from Renode log ([CTRL]) or simulator log ([RX-JSON]/[RX-BIN])."""
    ctrl_lines: list[str] = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                m = re.search(r'\[CTRL\]\s+(.*)', line) or re.search(r'\[RX-(?:JSON|BIN)\]\s+(.*)', line)
                if not m:
                    continue
                content = m.group(1).strip()
                # Only include actual gamepad state lines; skip startup/status messages
                if _GAMEPAD_LINE.match(content):
                    ctrl_lines.append(content)
    except FileNotFoundError:
        pass
    return ctrl_lines


def generate_report(sent_path: str, received_path: str, output_path: str) -> None:
    sent     = load_sent(sent_path)
    received = load_received(received_path)
    now      = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    rows = []
    matches = 0

    for i, entry in enumerate(sent):
        seq      = entry["seq"]
        exp_str  = expected_ctrl(entry)
        act_str  = received[i] if i < len(received) else "(missing)"
        ok       = _normalize(exp_str) == _normalize(act_str)
        if ok:
            matches += 1
        rows.append((seq, entry["time"], exp_str, act_str, ok))

    total     = len(sent)
    pass_rate = matches / total * 100 if total else 0.0

    pass_icon = "🟢 PASS" if pass_rate == 100 else ("🟡 PARTIAL" if pass_rate >= 80 else "🔴 FAIL")

    lines = [
        "# STM32 Controller Communication Test Report",
        "",
        f"> **Result: {pass_icon} — {pass_rate:.1f}%** ({matches}/{total} matched)  ",
        f"> Date: {now}",
        "",
        "## Test Configuration",
        "",
        f"| Item | Value |",
        f"|------|-------|",
        f"| Sent log | `{os.path.basename(sent_path)}` |",
        f"| Received log | `{os.path.basename(received_path)}` |",
        f"| Total packets sent | {total} |",
        f"| Total packets received | {len(received)} |",
        "",
        "## Packet Comparison",
        "",
        "| # | Time | Controller → STM32 (expected) | STM32 → UART3 (actual) | Result |",
        "|--:|------|-------------------------------|------------------------|:------:|",
    ]

    for seq, ts, exp, act, ok in rows:
        icon = "✅" if ok else "❌"
        # Highlight differences when failed
        if not ok and act != "(missing)":
            exp_set  = _normalize(exp)
            act_set  = _normalize(act)
            missing  = exp_set - act_set
            extra    = act_set - exp_set
            diff     = ""
            if missing:
                diff += f" ⚠️ missing: `{' '.join(sorted(missing))}`"
            if extra:
                diff += f" ⚠️ extra: `{' '.join(sorted(extra))}`"
            lines.append(f"| {seq} | {ts} | `{exp}` | `{act}`{diff} | {icon} |")
        else:
            lines.append(f"| {seq} | {ts} | `{exp}` | `{act}` | {icon} |")

    lines += [
        "",
        "## Summary",
        "",
        f"| | |",
        f"|---|---|",
        f"| **Overall result** | **{pass_icon}** |",
        f"| Pass rate | **{pass_rate:.1f}%** |",
        f"| Matched | {matches} / {total} |",
        f"| Failed | {total - matches} / {total} |",
        f"| Packets received by STM32 | {len(received)} |",
        "",
        "---",
        f"*Generated by compare.py — {now}*",
    ]

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(f"Report saved : {output_path}")
    print(f"Pass rate    : {pass_rate:.1f}%  ({matches}/{total})")
    if len(received) != total:
        print(f"WARNING: sent {total} packets but received {len(received)} lines")


def main() -> None:
    base = os.path.dirname(os.path.abspath(__file__))
    stm_base = os.path.join(base, "..", "cthrobt_stm")

    parser = argparse.ArgumentParser(description="Compare sent vs STM32-received packets")
    parser.add_argument("--sent", required=True,
                        help="JSONL log from controller.py --mock")
    parser.add_argument("--received",
                        default=os.path.join(stm_base, "received_signals.txt"),
                        help="Renode log from bridge.py (default: ../cthrobt_stm/received_signals.txt)")
    parser.add_argument("--output", default=None,
                        help="Output Markdown file (default: logs/test_report_<ts>.md)")
    args = parser.parse_args()

    if args.output is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        args.output = os.path.join(base, "logs", f"test_report_{ts}.md")

    generate_report(args.sent, args.received, args.output)


if __name__ == "__main__":
    main()
