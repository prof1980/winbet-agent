# 🎰 WinBet — Betting Odds Aggregator & Surebet Detector

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Mode: LIVE](https://img.shields.io/badge/mode-LIVE-red.svg)]()
[![Status: Active](https://img.shields.io/badge/status-active-success.svg)]()

Agente autonomo per la raccolta, normalizzazione e analisi di quote scommesse calcistiche da più bookmaker (SNAI, Eurobet, The Odds API) con rilevamento automatico di **surebet cross-bookmaker** e dashboard interattiva.

## ✨ Funzionalità

- 🕷️ **Multi-bookmaker scraping**: SNAI + Eurobet (TLS bypass via `curl_cffi`) + The Odds API
- 🔄 **Normalizzazione automatica**: dedup partite tra fonti con nomi/localizzazione diversi (italiano ↔ inglese)
- 💰 **Surebet detection**: calcolo automatico di arbitraggi profittevoli (cross-bookmaker)
- 📊 **Dashboard interattiva** Flask: layout 3 colonne, match cards collassabili, filtri bookmaker
- 📧 **Notifiche email** (Libero SMTP/IMAP): report giornaliero, monitor comandi remoti
- ⏰ **Cronjob automatici**: scrape ogni 2 ore + report giornaliero alle 8:00
- 🗄️ **Database SQLite**: schema normalizzato, history tracking, cleanup automatico
- 📈 **Storico completo**: variazioni quote, trend nel tempo

## 🏗️ Architettura (3 livelli)

```
WinBet/
├── directives/      # SOP in Markdown (cosa fare)
├── execution/       # Script Python deterministici (come fare)
├── config/          # File configurazione (markets, bookmakers)
├── scripts/         # Script bash ausiliari
├── .env.example     # Template credenziali
├── install.sh       # Installazione automatica
├── requirements.txt # Dipendenze Python
└── winbet_config.json  # Modalità/interval/bookmaker
```

## 🚀 Quick Start

### Prerequisiti
- Linux/macOS/WSL2
- Python 3.10+
- 500 MB disco + 1 GB RAM

### Installazione (3 passi)

```bash
# 1. Clona e installa
git clone https://github.com/<your-username>/winbet-agent.git
cd winbet-agent
chmod +x install.sh
./install.sh

# 2. Configura credenziali
cp .env.example .env
nano .env  # inserisci THE_ODDS_API_KEY, LIBERO_EMAIL, LIBERO_PASSWORD, DAILY_REPORT_TO

# 3. Test rapido
./venv/bin/python execution/libero_notifier.py test-send
./venv/bin/python execution/scrape_unified_v2.py --sources snai,eurobet --store-db
```

### Avvio dashboard
```bash
./venv/bin/python execution/dashboard.py
# → http://localhost:8080
```

## 📋 Modalità operative

### LIVE (default, produzione)
```json
{"mode": "LIVE", "interval_minutes": 120}
```
Scraping reale ogni 2 ore da SNAI + Eurobet + The Odds API (1×/giorno).

### DEMO (test/sviluppo)
```json
{"mode": "DEMO"}
```
Dati generati per test pipeline senza dipendere da bookmaker live.

## 🔌 Fonti dati

| Fonte | Metodo | Frequenza | Costo |
|---|---|---|---|
| **SNAI** | curl_cffi + TLS impersonation | Ogni 2 ore | Gratis |
| **Eurobet** | curl_cffi + TLS impersonation | Ogni 2 ore | Gratis |
| **The Odds API** | REST API con key | 1 volta/giorno | ~60 crediti/mese (free 500) |

## 📧 Notifiche

### Email giornaliera automatica (8:00)
Ogni mattina ricevi report completo a `DAILY_REPORT_TO`:
- Stato sistema (DB, disco, bookmaker attivi)
- Top 10 surebet profittevoli
- Cronologia scraping ultimi 7 giorni
- Statistiche per bookmaker e lega

### Comandi email (via Libero IMAP)
Invia email a `LIBERO_EMAIL` con subject che inizi con:

| Comando | Risposta |
|---|---|
| `status` | Report DB + scraper + bookmaker |
| `surebet` | Surebet attive ≥1% |
| `matches <lega>` | Es. "matches serie a" |
| `odds <squadra>` | Es. "odds Inter" |
| `stop` / `start` | Pausa/riprendi scraper |
| `help` | Lista comandi |

## ⏰ Schedulazione automatica (cronjob)

Crea 5 cronjob con `hermes cronjob`:

```bash
# 1. Scraping principale SNAI+Eurobet (ogni 2h)
hermes cronjob create --name "WinBet Scraper 2h" \
  --schedule "0 */2 * * *" --no-agent \
  --script "winbet_scrape_cycle.sh" --workdir "/path/to/winbet-agent"

# 2. The Odds API (1 volta/giorno alle 9:00)
hermes cronjob create --name "WinBet The Odds API Daily" \
  --schedule "0 9 * * *" \
  --prompt "cd /path/to/winbet-agent && ./venv/bin/python execution/the_odds_api_scraper.py --sports mondiali"

# 3. Email Monitor IMAP (ogni 10 min)
hermes cronjob create --name "WinBet Email Monitor" \
  --schedule "every 10m" \
  --prompt "cd /path/to/winbet-agent && ./venv/bin/python execution/winbet_email_handler.py monitor --interval 300"

# 4. Report giornaliero (8:00)
hermes cronjob create --name "WinBet Daily Report 8:00" \
  --schedule "0 8 * * *" \
  --prompt "cd /path/to/winbet-agent && ./venv/bin/python execution/winbet_daily_report.py --to \${DAILY_REPORT_TO}"
```

## 🛠️ Comandi CLI

```bash
# Scraping
./venv/bin/python execution/scrape_unified_v2.py --sources snai,eurobet --store-db
./venv/bin/python execution/the_odds_api_scraper.py --sports mondiali

# Surebet
./venv/bin/python execution/surebet_detector.py

# Deduplica e merge partite
./venv/bin/python execution/dedupe_matches.py --backup

# Dashboard
./venv/bin/python execution/dashboard.py

# Report
./venv/bin/python execution/winbet_daily_report.py --to your@email.com --dry-run

# Notifiche email
./venv/bin/python execution/libero_notifier.py test-send
./venv/bin/python execution/winbet_email_handler.py monitor --interval 60
```

## 📊 Stack tecnologico

- **Backend**: Python 3.10+, Flask, SQLite
- **Scraping**: `curl_cffi` (TLS impersonation), `requests`, `beautifulsoup4`
- **API**: The Odds API v4
- **Email**: `smtplib`, `imaplib` (stdlib), `python-dotenv`
- **Database**: SQLite (zero-config, embedded)
- **Automation**: Hermes cronjob, bash scripts

## 🐛 Troubleshooting

| Problema | Soluzione |
|---|---|
| SNAI/Eurobet scraping fallisce | Aggiorna `curl_cffi`: `pip install --upgrade curl-cffi` |
| The Odds API errore 401 | Verifica `THE_ODDS_API_KEY` in `.env` |
| SMTP Libero errore | Verifica `LIBERO_EMAIL`/`LIBERO_PASSWORD` e account verificato |
| Dashboard non si avvia | Controlla porta 8080 libera, vedi `winbet_config.json` |
| Partite duplicate nel DB | Esegui `./venv/bin/python execution/dedupe_matches.py --backup` |

## 📚 Documentazione

- `directives/` — SOP dettagliate per ogni componente
- `REPLICA_SETUP.md` — guida completa replica
- `directives/notifications_libero.md` — setup email
- `directives/daily_report.md` — report giornaliero

## 🔒 Sicurezza

- ⚠️ **MAI committare `.env`** — contiene credenziali sensibili
- `.gitignore` esclude automaticamente: `.env`, `*.db`, `*.log`, `__pycache__/`, `venv/`, `*.pid`
- Permessi `.env`: `chmod 600`
- Verifica: `git status` non deve mai mostrare `.env`

## ⚖️ Note legali

> **⚠️ Importante**: questo tool è fornito a scopo **educativo e di ricerca personale**.

- Lo scraping di siti bookmaker può violare i loro Termini di Servizio
- Gli autori non si ritengono responsabili per l'uso improprio
- Si raccomanda l'uso di **The Odds API** (via legale) come fonte primaria
- L'utente è l'unico responsabile per la conformità legale del proprio uso

## 📄 Licenza

MIT License — vedi [LICENSE](LICENSE) per dettagli.

---

🤖 **WinBet Agent** • Creato con ❤️ per automatizzare l'analisi delle quote calcistiche
