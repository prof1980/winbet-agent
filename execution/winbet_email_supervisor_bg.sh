#!/usr/bin/env bash
# WinBet Email Supervisor — Persistent daemon
# This process itself runs continuously; the monitor Python is spawned detached.

LOGFILE="/mnt/c/Users/angel/WinBet/logs/winbet_email_supervisor.log"
MONITOR_LOG="/mnt/c/Users/angel/WinBet/logs/winbet_email_handler.log"
PROJECT="/mnt/c/Users/angel/WinBet"
PYTHON="$PROJECT/venv/bin/python"
SCRIPT="$PROJECT/execution/winbet_email_handler.py"
INTERVAL=300

mkdir -p "$PROJECT/logs"

date_log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

while true; do
    # Check for existing monitor
    PID=$(pgrep -f "winbet_email_handler.py monitor --interval $INTERVAL" | head -n1)
    if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
        # Monitor is alive
        date_log "Monitor OK (PID $PID)" >> "$LOGFILE"
    else
        # Start detached monitor
        date_log "Monitor non trovato. Avvio..." >> "$LOGFILE"
        cd "$PROJECT" || exit 1
        nohup "$PYTHON" "$SCRIPT" monitor --interval "$INTERVAL" >> "$MONITOR_LOG" 2>&1 </dev/null &
        NEW_PID=$!
        date_log "Monitor avviato con PID $NEW_PID" >> "$LOGFILE"
        # Give the monitor a chance to start up before looping
        sleep 15
    fi
    sleep 30
done
