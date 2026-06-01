#!/bin/bash
echo "=== Standalone Simulator (macOS/Linux) ==="
echo "Listens on 127.0.0.1:7777 -- use instead of bridge.py for debug without Renode"
echo
cd "$(dirname "$0")/.."
python3 simulator.py
