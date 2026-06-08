#!/usr/bin/env bash
set -euo pipefail

WINBET_DIR="/mnt/c/Users/angel/WinBet"
PYTHON="${WINBET_DIR}/venv/bin/python"
SCRIPT="${WINBET_DIR}/execution/winbet_email_handler.py"
INTERVAL=300
RESTART_SECS=10
LOGFILE="${WINBET_DIR}/execution/winbet_supervisor.log"

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" | tee -a "$LOGFILE"
}

cleanup() {
    log "Supervisore terminato."
    exit 0
}
trap cleanup SIGTERM SIGINT

log "=== Supervisore avviato ==="

while true; do
    log "Avvio monitor..."
    if "$PYTHON" "$SCRIPT" monitor --interval "$INTERVAL"; then
        log "Monitor uscito con codice 0. Riavvio tra ${RESTART_SECS}s..."
    else
        log "Monitor uscito con codice $?. Riavvio tra ${RESTART_SECS}s..."
    fi
    sleep "$RESTART_SECS"
done
