#!/usr/bin/env bash
# Supervisor per winbet_email_handler — riavvia automaticamente se il processo termina

LOG="/mnt/c/Users/angel/WinBet/execution/winbet_email_supervisor.log"
PIDFILE="/mnt/c/Users/angel/WinBet/execution/.winbet_email_handler.pid"
MONITOR_CMD="./venv/bin/python execution/winbet_email_handler.py monitor --interval 300"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Supervisor avviato (PID $$)" >> "$LOG"

while true; do
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Avvio monitor WinBet..." >> "$LOG"
    cd /mnt/c/Users/angel/WinBet || { echo "Errore cd"; sleep 30; continue; }
    $MONITOR_CMD >> "$LOG" 2>&1
    CODE=$?
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Monitor terminato con exit code $CODE. Riavvio in 10 secondi..." >> "$LOG"
    sleep 10
done
