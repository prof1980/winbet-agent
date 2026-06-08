#!/bin/bash
# WinBet - Script di installazione e setup
# Uso: ./install.sh

set -e

echo "=================================================="
echo "  WinBet - Installazione e Setup"
echo "=================================================="

# 1. Crea venv
if [ ! -d "venv" ]; then
    echo "[1/5] Creazione ambiente virtuale..."
    python3 -m venv venv
else
    echo "[1/5] venv già esistente, skip"
fi

# 2. Attiva venv
source venv/bin/activate

# 3. Installa dipendenze
echo "[2/5] Installazione dipendenze Python..."
pip install --upgrade pip
pip install -r requirements.txt

# 4. Installa browser Playwright
echo "[3/5] Installazione Playwright Chromium..."
playwright install chromium

# 5. Crea .env da .env.example se non esiste
if [ ! -f ".env" ]; then
    echo "[4/5] Creazione .env da .env.example..."
    cp .env.example .env
    chmod 600 .env
    echo "  ⚠ IMPORTANTE: edita .env con le tue credenziali!"
    echo "    nano .env"
else
    echo "[4/5] .env già esistente, skip"
fi

# 6. Crea directory necessarie
echo "[5/5] Creazione directory..."
mkdir -p .tmp logs

echo ""
echo "=================================================="
echo "  ✅ Installazione completata!"
echo "=================================================="
echo ""
echo "Prossimi passi:"
echo "  1. Configura le credenziali:  nano .env"
echo "  2. Test invio email:          ./venv/bin/python execution/libero_notifier.py test-send"
echo "  3. Test scraping SNAI:        ./venv/bin/python execution/scrape_unified_v2.py --sources snai --store-db"
echo "  4. Test scraping Eurobet:     ./venv/bin/python execution/scrape_unified_v2.py --sources eurobet --store-db"
echo "  5. Test The Odds API:         ./venv/bin/python execution/the_odds_api_scraper.py"
echo "  6. Test report giornaliero:   ./venv/bin/python execution/winbet_daily_report.py --to your_email@gmail.com --dry-run"
echo "  7. Avvia dashboard:           ./venv/bin/python execution/dashboard.py"
echo ""
echo "Schedulazione automatica: vedi sezione 'Setup Cronjob' nel README.md"
