#!/bin/bash
# WinBet Email Monitor Supervisor — mantiene il monitor in esecuzione continua
# Rilancia automaticamente il processo se termina (anche con codice 0)
# Log: /mnt/c/Users/angel/WinBet/logs/monitor_supervisor_YYYYMMDD.log

DIR="/mnt/c/Users/angel/WinBet"
LOGDIR="$DIR/logs"
LOGFILE="$LOGDIR/monitor_supervisor_$(date +%Y%m%d).log"
MONITOR_LOG="$LOGDIR/winbet_email_monitor.log"
PYTHON="$DIR/venv/bin/python"
SCRIPT="$DIR/execution/winbet_email_handler.py"
PIDFILE="$DIR/.tmp/supervisor.pid"
INTERVAL=300

mkdir -p "$LOGDIR" "$DIR/.tmp"

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') [SUPERVISOR] $1" | tee -a "$LOGFILE"
}

# Rimuovi vecchio PID file del monitor (altrimenti il monitor esce subito)
cleanup_stale() {
    rm -f "$DIR/execution/.winbet_email_handler.pid"
}

# Verifica se il monitor è effettivamente attivo e funzionante
is_monitor_alive() {
    local pid
    pid=$(pgrep -f "$SCRIPT monitor")
    if [ -n "$pid" ]; then
        if kill -0 "$pid" 2>/dev/null; then
            return 0
        fi
    fi
    return 1
}

# Lancia il monitor
start_monitor() {
    cleanup_stale
    cd "$DIR" || exit 1
    nohup "$PYTHON" "$SCRIPT" monitor --interval "$INTERVAL" >> "$MONITOR_LOG" 2>&1 &
    local newpid=$!
    sleep 3
    if kill -0 "$newpid" 2>/dev/null; then
        log "Monitor avviato con PID $newpid"
        return 0
    else
        log "ERRORE: monitor PID $newpid non attivo dopo 3s"
        return 1
    fi
}

# ---- MAIN ----
echo $$ > "$PIDFILE"
log "Supervisor avviato (PID $$)"

# Loop infinito di supervisione
while true; do
    if ! is_monitor_alive; then
        log "Monitor non trovato o morto. Riavvio..."
        start_monitor || log "Riavvio fallito, riprovo al prossimo ciclo"
    fi
    sleep 60
done
