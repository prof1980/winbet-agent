#!/usr/bin/env bash
# WinBet Email Supervisor Daemon — avvia e mantiene attivo winbet_email_handler.py
# Lanciare con: nohup bash /mnt/c/Users/angel/WinBet/execution/winbet_email_supervisor_daemon.sh > /dev/null 2>&1 &

APP_DIR="/mnt/c/Users/angel/WinBet"
PYTHON="$APP_DIR/venv/bin/python"
SCRIPT="$APP_DIR/execution/winbet_email_handler.py"
LOGFILE="$APP_DIR/execution/winbet_email_supervisor_daemon.log"
INTERVAL=5

log() {
    local line="$(date '+%Y-%m-%d %H:%M:%S') [DAEMON] $1"
    echo "$line" | tee -a "$LOGFILE"
}

# Verifica che il PID nel file .pid corrisponda a un processo attivo
check_alive() {
    if [ -f "$APP_DIR/execution/.winbet_email_handler.pid" ]; then
        local pid
        pid=$(cat "$APP_DIR/execution/.winbet_email_handler.pid")
        if kill -0 "$pid" 2>/dev/null; then
            return 0
        fi
    fi
    return 1
}

# Avvia il processo Python in background
start_handler() {
    log "Avvio winbet_email_handler.py..."
    cd "$APP_DIR" || { log "ERRORE: cd fallito"; exit 1; }
    # Rimuovi file PID vecchio
    rm -f "$APP_DIR/execution/.winbet_email_handler.pid"
    # Avvia con nohup in background
    nohup "$PYTHON" "$SCRIPT" monitor --interval 300 > "$APP_DIR/execution/winbet_email_handler_live.log" 2>&1 &
    local new_pid=$!
    sleep 2
    if kill -0 "$new_pid" 2>/dev/null; then
        log "Avviato con PID $new_pid"
    else
        log "AVVIO FALLITO — riprovo al prossimo ciclo"
    fi
}

# Ciclo principale
log "Daemon supervisor avviato"
while true; do
    if ! check_alive; then
        start_handler
    fi
    sleep "$INTERVAL"
done
