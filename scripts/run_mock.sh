#!/bin/bash
set -e
echo "=== Mock Controller (macOS/Linux) ==="
cd "$(dirname "$0")/.."

COUNT=${1:-20}
INTERVAL=${2:-0.5}

echo "Sending $COUNT random packets at ${INTERVAL}s interval"
python3 controller.py --mock --mock-count "$COUNT" --mock-interval "$INTERVAL"
