#!/bin/bash
set -e
echo "=== Compare sent vs received (macOS/Linux) ==="
cd "$(dirname "$0")/.."

# Find latest mock sent log
SENT=$(ls -t logs/mock_sent_*.jsonl 2>/dev/null | head -1)
if [ -z "$SENT" ]; then
    echo "ERROR: No mock_sent_*.jsonl found in logs/"
    echo "Run scripts/run_mock.sh first."
    exit 1
fi

echo "Using sent log: $SENT"
python3 compare.py --sent "$SENT"
echo ""
echo "Report saved to logs/test_report_*.md"
