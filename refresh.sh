#!/bin/bash
# Regenerate the VWRP screen. Invoked by the launchd agent on a schedule,
# and safe to run by hand at any time.
set -u
cd "$(dirname "$0")" || exit 1

LOG="output/refresh.log"
mkdir -p output

# Keep the log from growing without bound.
if [ -f "$LOG" ] && [ "$(wc -c < "$LOG")" -gt 200000 ]; then
    tail -n 200 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
fi

echo "=== $(date '+%Y-%m-%d %H:%M:%S') starting refresh ===" >> "$LOG"

if ! ping -c 1 -t 5 query1.finance.yahoo.com > /dev/null 2>&1; then
    echo "no network / Yahoo unreachable - skipping this run" >> "$LOG"
    exit 0
fi

# --refresh bypasses the 24h cache so fundamentals are genuinely re-pulled.
./venv/bin/python -W ignore screener.py --top 150 --refresh >> "$LOG" 2>&1
status=$?

if [ $status -eq 0 ]; then
    echo "=== $(date '+%Y-%m-%d %H:%M:%S') refresh OK ===" >> "$LOG"
else
    echo "=== $(date '+%Y-%m-%d %H:%M:%S') refresh FAILED (exit $status) ===" >> "$LOG"
fi
exit $status
