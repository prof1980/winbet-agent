#!/usr/bin/env bash
# WinBet Email Monitor Supervisor
# Controlla che winbet_email_handler.py monitor continui a girare
# Se morto, riavvia. Se email "stop" conferma e marca come letta.
# Se email "start" conferma e marca come letta.

set -euo pipefail

PROJECT_ROOT="/mnt/c/Users/angel/WinBet"
SCRIPT="${PROJECT_ROOT}/execution/winbet_email_handler.py"
INTERVAL=300
PID_FILE="${PROJECT_ROOT}/.tmp/.winbet_email_handler.pid"
LOG_FILE="${PROJECT_ROOT}/.tmp/winbet_email_handler.log"
SUPERVISOR_LOG="${PROJECT_ROOT}/.tmp/winbet_supervisor.log"
VENV_PYTHON="${PROJECT_ROOT}/venv/bin/python"

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S')  $*" | tee -a "$SUPERVISOR_LOG"
}

mkdir -p "${PROJECT_ROOT}/.tmp"

is_running() {
    if [[ -f "$PID_FILE" ]]; then
        local pid
        pid=$(cat "$PID_FILE")
        if kill -0 "$pid" 2>/dev/null; then
            return 0
        fi
    fi
    return 1
}

start_monitor() {
    log "Avvio monitor WinBet..."
    cd "$PROJECT_ROOT"
    nohup "$VENV_PYTHON" "$SCRIPT" monitor --interval $INTERVAL >> "$LOG_FILE" 2>&1 &
    sleep 1
    if is_running; then
        log "Monitor avviato con PID $(cat "$PID_FILE")"
    else
        log "❌ ERRORE: Impossibile avviare monitor"
    fi
}

# Main loop supervisione
check_and_revive() {
    while true; do
        if ! is_running; then
            log "⚠️ Monitor non trovato o morto, riavvio in corso..."
            start_monitor
        fi
        sleep 60
    done
}

# Entry point
if pgrep -f "winbet_monitor_supervisor.sh" | grep -v $$ > /dev/null; then
    log "Supervisor già in esecuzione. Esco."
    exit 0
fi

log "Supervisor WinBet avviato (PID $$)"
check_and_revive
