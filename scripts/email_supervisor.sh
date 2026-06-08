#!/usr/bin/env bash
# Email Monitor Supervisor — riavvia automaticamente se il monitor muore
# Evita duplicati tramite PID file

WORK_DIR="/mnt/c/Users/angel/WinBet"
PYTHON="$WORK_DIR/venv/bin/python"
SCRIPT="$WORK_DIR/execution/winbet_email_handler.py"
LOGFILE="$WORK_DIR/logs/email_supervisor.log"
MONITOR_LOG="$WORK_DIR/logs/email_monitor.log"
PIDFILE="$WORK_DIR/.email_supervisor.pid"

log() {
    echo "[$(date +%Y-%m-%d\ %H:%M:%S)] $1" | tee -a "$LOGFILE"
}

# Blocco anti-duplicato
if [ -f "$PIDFILE" ]; then
    OLD_PID=$(cat "$PIDFILE" 2>/dev/null)
    if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
        log "Supervisor già attivo (PID=$OLD_PID). Uscita."
        exit 0
    fi
fi

echo $$ > "$PIDFILE"

# Assicura che i log esistano
touch "$LOGFILE" "$MONITOR_LOG" 2>/dev/null

log "Supervisor avviato. Work dir: $WORK_DIR"

# Pulizia PID file all'uscita
trap 'rm -f "$PIDFILE"; log "Supervisor terminato."; exit 0' EXIT INT TERM

while true; do
    # Cerca processo esistente
    PID=$(pgrep -f "winbet_email_handler.py monitor")

    if [ -n "$PID" ]; then
        # Processo attivo: verifica se risponde (log recenti?)
        LAST_LOG=0
        if [ -f "$MONITOR_LOG" ]; then
            LAST_LOG=$(stat -c %Y "$MONITOR_LOG" 2>/dev/null || echo 0)
        fi
        NOW=$(date +%s)
        AGE=$((NOW - LAST_LOG))

        if [ "$AGE" -gt 900 ] && [ "$LAST_LOG" -gt 0 ]; then
            log "WARNING: Nessun log da ${AGE}s (soglia 900s). Kill e restart del monitor PID=$PID"
            kill "$PID" 2>/dev/null
            sleep 3
            kill -9 "$PID" 2>/dev/null
        else
            # Tutto ok: ri-verifica tra 30 secondi
            sleep 30
            continue
        fi
    fi

    # Nessun processo trovato: avvia
    log "Nessun monitor attivo. Avvio nuova istanza..."
    cd "$WORK_DIR" || { log "ERRORE: cd fallito"; sleep 60; continue; }

    # Avvia monitor in background
    cd "$WORK_DIR"
    "$PYTHON" "$SCRIPT" monitor --interval 300 >> "$MONITOR_LOG" 2>&1 &
    MONITOR_PID=$!

    sleep 5
    if kill -0 "$MONITOR_PID" 2>/dev/null; then
        log "Monitor avviato con successo (PID=$MONITOR_PID)"
    else
        log "ERRORE: Monitor morto subito dopo avvio. Retry tra 30s..."
        sleep 30
        continue
    fi
done
