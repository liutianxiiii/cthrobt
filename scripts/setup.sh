#!/bin/bash
set -e
echo "=== cthrobt setup (macOS/Linux) ==="
cd "$(dirname "$0")/.."
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt
echo ""
echo "Setup complete. You can now run:"
echo "  scripts/run_mock.sh       -- send random gamepad packets to STM32"
echo "  scripts/run_simulator.sh  -- start standalone debug simulator"
echo "  scripts/compare.sh        -- generate test report"
