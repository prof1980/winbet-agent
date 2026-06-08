#!/usr/bin/env bash
# WinBet Email Monitor — keep-alive wrapper
# Se il processo Python termina, viene riavviato automaticamente

PROJECT_DIR="/mnt/c/Users/angel/WinBet"
PYTHON="$PROJECT_DIR/venv/bin/python"
HANDLER="$PROJECT_DIR/execution/winbet_email_handler.py"
INTERVAL=300
LOG_FILE="$PROJECT_DIR/logs/winbet_email_monitor.log"
PID_FILE="/tmp/winbet_email_monitor.pid"

# Crea directory log se mancante
mkdir -p "$PROJECT_DIR/logs"

# Scrive PID
echo $$ > "$PID_FILE"

exec >> "$LOG_FILE" 2>&1

echo "====== [$(date '+%Y-%m-%d %H:%M:%S')] WinBet email monitor wrapper avviato (PID $$) ======"

while true; do
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Avvio monitor Python..."
    cd "$PROJECT_DIR" || exit 1
    # Carica variabili d'ambiente da .env
    if [ -f "$PROJECT_DIR/.env" ]; then
        set -a
        source "$PROJECT_DIR/.env"
        set +a
    fi
    "$PYTHON" "$HANDLER" monitor --interval "$INTERVAL"
    EXIT_CODE=$?
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Monitor terminato con exit code $EXIT_CODE. Riavvio tra 10s..."
    sleep 10
done
