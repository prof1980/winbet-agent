#!/bin/bash
# WinBet Scrape Cycle — Eseguito ogni 2 ore dal cronjob
# Modalità LIVE: scraping REALE da SNAI e Eurobet
# The Odds API è eseguito separatamente 1 volta/giorno (cronjob dedicato)
# per rimanere entro il budget di 500 crediti/mese free
#
# Budget:
# - SNAI + Eurobet: illimitato (scraping diretto, no API)
# - The Odds API: 1 chiamata/giorno × ~2 crediti = 60 crediti/mese ✅ entro budget
cd /mnt/c/Users/angel/WinBet

source /tmp/venvtemp/bin/activate 2>/dev/null

EMAIL_FLAG=""
if [ "${WINBET_EMAIL:-0}" = "1" ]; then
    EMAIL_FLAG="--email"
    echo "Email notifications: ON"
fi

MODE=$(python3 -c "import json; print(json.load(open('winbet_config.json'))['mode'])" 2>/dev/null || echo "DEMO")
echo "Modalità: $MODE (ogni 2 ore: solo SNAI + Eurobet)"
echo "$(date '+%Y-%m-%d %H:%M:%S') === SCRAPE START ==="

# 1. Scraping SNAI + Eurobet (curl_cffi TLS impersonation)
echo "[1/4] Scraping SNAI + Eurobet..."
./venv/bin/python execution/scrape_unified_v2.py --sources snai,eurobet --store-db --output /tmp/scrape_be_$(date +%s).json

# 2. Surebet detection
echo "[2/4] Surebet detection..."
./venv/bin/python execution/surebet_detector.py

# 3. Notifiche Telegram/Discord (via Hermes)
echo "[3/4] Notifiche canali..."
./venv/bin/python execution/notifications.py surebets

# 4. Email report (se abilitato)
if [ -n "$EMAIL_FLAG" ]; then
    echo "[4/4] Email report..."
    ./venv/bin/python execution/scheduler.py --once $EMAIL_FLAG
else
    echo "[4/4] Email report: SKIP (set WINBET_EMAIL=1 per abilitare)"
fi

echo "$(date '+%Y-%m-%d %H:%M:%S') === SCRAPE DONE ==="
