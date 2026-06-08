#!/bin/bash
# Supervisor loop per cronjob: mantiene winbet_email_handler.py monitor attivo
LOG="/mnt/c/Users/angel/WinBet/logs/cron_supervisor.log"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Cron supervisor avviato" >> "$LOG"
while true; do
  if ! pgrep -f "winbet_email_handler.py monitor" >/dev/null 2>&1; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Monitor non attivo: riavvio..." >> "$LOG"
    cd /mnt/c/Users/angel/WinBet && ./venv/bin/python execution/winbet_email_handler.py monitor --interval 300 >> logs/winbet_email_monitor.log 2>&1 &
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Monitor riavviato (PID $!)" >> "$LOG"
  fi
  sleep 60
done
