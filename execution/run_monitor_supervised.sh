#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}/.."
while true; do
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] Avvio winbet_email_handler.py monitor..."
    ./venv/bin/python execution/winbet_email_handler.py monitor --interval 300 || true
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] Processo terminato, riavvio tra 5 secondi..."
    sleep 5
done
