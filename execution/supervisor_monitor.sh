#!/bin/bash
cd /mnt/c/Users/angel/WinBet
LOGFILE="execution/supervisor_monitor.log"

# Log with timestamps
log_msg() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" | tee -a "$LOGFILE"
}

# Kill any existing python winbet_email_handler processes
log_msg "Killing existing winbet_email_handler processes..."
pkill -f "winbet_email_handler.py monitor" 2>/dev/null
sleep 2

log_msg "Starting WinBet Email Monitor supervisor loop..."

LOOP_COUNT=0
while true; do
    LOOP_COUNT=$((LOOP_COUNT + 1))
    log_msg "=== Iteration $LOOP_COUNT: launching monitor ==="
    ./venv/bin/python execution/winbet_email_handler.py monitor --interval 300
    EXIT_CODE=$?
    log_msg "Monitor exited with code $EXIT_CODE. Restarting in 10 seconds..."
    sleep 10
done
