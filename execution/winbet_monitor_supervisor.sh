#!/usr/bin/env bash
# WinBet Email Monitor Supervisor
# Mantiene in esecuzione continua il monitor email WinBet.
# Se il processo termina per qualsiasi motivo, viene riavviato automaticamente.
# Utilizzo:
#   ./execution/winbet_monitor_supervisor.sh
# Oppure in background:
#   nohup ./execution/winbet_monitor_supervisor.sh > supervisor.log 2>&1 &

set -euo pipefail

PROJECT_ROOT="/mnt/c/Users/angel/WinBet"
VENV_PYTHON="$PROJECT_ROOT/venv/bin/python"
HANDLER_SCRIPT="$PROJECT_ROOT/execution/winbet_email_handler.py"
PID_FILE="$PROJECT_ROOT/execution/.winbet_email_handler.pid"
LOG_FILE="$PROJECT_ROOT/supervisor.log"
INTERVAL=300

log_msg() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') [SUPERVISOR] $1" | tee -a "$LOG_FILE"
}

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
    log_msg "Avvio monitor WinBet email (interval=${INTERVAL}s) ..."
    cd "$PROJECT_ROOT"
    # Avvia in background disowned così sopravvive anche se il supervisor chiude
    nohup "$VENV_PYTHON" "$HANDLER_SCRIPT" monitor --interval "$INTERVAL" \
        >> "$PROJECT_ROOT/winbet_monitor.log" 2>&1 &
    local new_pid=$!
    echo "$new_pid" > "$PID_FILE"
    log_msg "Monitor avviato con PID $new_pid"
}

# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
log_msg "Supervisor avviato. Controllo ogni 60s."

while true; do
    if ! is_running; then
        log_msg "Monitor non in esecuzione (o PID file stale). Riavvio ..."
        start_monitor
    fi
    sleep 60
done
