# WinBet - Replica Setup

Questo ZIP contiene l'agente WinBet completo, **escluso**:
- ❌ `venv/` — ambiente virtuale Python (rigenerato con `install.sh`)
- ❌ `.env` — credenziali (devi crearlo tu con `cp .env.example .env`)
- ❌ `winbet.db` — database (rigenerato al primo scrape)
- ❌ `__pycache__/`, `*.pyc` — cache Python

## Requisiti di Sistema

- **OS**: Linux (testato su Ubuntu 22.04 WSL), macOS, o Windows con WSL2
- **Python**: 3.10 o superiore
- **RAM**: minimo 1 GB disponibile
- **Disco**: 500 MB (venv + dipendenze + DB)
- **Rete**: accesso internet a SNAI, Eurobet, the-odds-api.com, smtp.libero.it

## Installazione Rapida

```bash
# 1. Estrai ZIP
unzip WinBet_*.zip
cd WinBet

# 2. Esegui installazione automatica
chmod +x install.sh
./install.sh

# 3. Configura credenziali
nano .env
# Inserisci: THE_ODDS_API_KEY, LIBERO_EMAIL, LIBERO_PASSWORD, DAILY_REPORT_TO

# 4. Test rapido
./venv/bin/python execution/libero_notifier.py test-send
./venv/bin/python execution/scrape_unified_v2.py --sources snai,eurobet --store-db
```

## Configurazione Cronjob (Opzionale)

WinBet è progettato per girare in background con cronjob. Crea 5 job con `hermes cronjob`:

### 1. Scraping principale SNAI + Eurobet (ogni 2 ore)
```bash
hermes cronjob create \
  --name "WinBet Scraper 2h" \
  --schedule "0 */2 * * *" \
  --no-agent \
  --script "winbet_scrape_cycle.sh" \
  --workdir "/path/to/WinBet"
```

### 2. The Odds API (1 volta/giorno alle 9:00)
```bash
hermes cronjob create \
  --name "WinBet The Odds API Daily" \
  --schedule "0 9 * * *" \
  --prompt "Esegui: cd /path/to/WinBet && ./venv/bin/python execution/the_odds_api_scraper.py --sports mondiali"
```

### 3. Email Monitor IMAP (ogni 10 min)
```bash
hermes cronjob create \
  --name "WinBet Email Monitor" \
  --schedule "every 10m" \
  --prompt "Esegui: cd /path/to/WinBet && ./venv/bin/python execution/winbet_email_handler.py monitor --interval 300"
```

### 4. Report giornaliero (8:00)
```bash
hermes cronjob create \
  --name "WinBet Daily Report 8:00" \
  --schedule "0 8 * * *" \
  --prompt "Esegui: cd /path/to/WinBet && ./venv/bin/python execution/winbet_daily_report.py --to \${DAILY_REPORT_TO}"
```

## Architettura (3 livelli)

```
WinBet/
├── README.md                    # Questo file
├── install.sh                   # Script di installazione
├── requirements.txt             # Dipendenze Python
├── .env.example                 # Template credenziali (copia in .env)
├── winbet_config.json           # Configurazione modalità/interval/bookmaker
├── config/                      # File di configurazione aggiuntivi
│   ├── markets.json             # Tipologie di mercato (1X2, Over/Under, ecc.)
│   └── bookmakers.json          # Configurazione bookmaker (selettori CSS, API)
├── directives/                  # SOP (Markdown) - Cosa fare
│   ├── scraping.md
│   ├── database.md
│   ├── daily_report.md
│   ├── notifications_libero.md
│   └── ...
├── execution/                   # Script Python - Come fare
│   ├── scrapers/                # SNAI, Eurobet, The Odds API
│   ├── notifiers/               # Libero SMTP/IMAP
│   ├── dashboard.py             # Server Flask
│   ├── scrape_unified_v2.py     # Orchestratore
│   ├── surebet_detector.py      # Rilevamento surebet
│   └── ...
├── scripts/                     # Script bash ausiliari
└── logs/                        # Log di runtime (auto-generati)
```

## Modalità di Esecuzione

### LIVE (default, produzione)
```json
{"mode": "LIVE", "interval_minutes": 120}
```
Scraping reale da SNAI, Eurobet e The Odds API. Richiede connessione internet.

### DEMO (test/sviluppo)
```json
{"mode": "DEMO"}
```
Usa dati generati per testare pipeline senza dipendere da bookmaker live.

## Comandi Rapidi

```bash
# Scraping
./venv/bin/python execution/scrape_unified_v2.py --sources snai,eurobet --store-db
./venv/bin/python execution/the_odds_api_scraper.py

# Surebet detection
./venv/bin/python execution/surebet_detector.py

# Dashboard
./venv/bin/python execution/dashboard.py
# → http://localhost:8080

# Report
./venv/bin/python execution/winbet_daily_report.py --to your@email.com --dry-run
./venv/bin/python execution/winbet_daily_report.py --to your@email.com

# Notifiche email
./venv/bin/python execution/libero_notifier.py test-send
./venv/bin/python execution/libero_notifier.py test-fetch
./venv/bin/python execution/winbet_email_handler.py monitor --interval 60

# Configurazione
nano winbet_config.json
nano .env
```

## Comandi Email (via Libero)

Invia email a `LIBERO_EMAIL` con subject o body che inizi con:

| Comando | Esempio | Risposta |
|---|---|---|
| `status` | `[WinBet] status` | Report DB + scraper + bookmaker |
| `surebet` | `surebet` | Surebet attive ≥1% |
| `matches <lega>` | `matches serie a` | Partite di quella lega |
| `odds <squadra>` | `odds Inter` | Quote per quella squadra |
| `stop` / `start` | `stop` | Pausa/riprendi scraper |
| `help` | `help` | Lista comandi |

## Troubleshooting

### Errore TLS scraping SNAI/Eurobet
- SNAI ed Eurobet hanno protezione anti-bot (fingerprint TLS)
- Lo script usa `curl_cffi` con `impersonate='chrome136'` per bypassare
- Se fallisce, aggiorna curl_cffi: `pip install --upgrade curl-cffi`

### Errore 401 The Odds API
- Verifica che `THE_ODDS_API_KEY` in `.env` sia corretta
- Controlla crediti residui: https://the-odds-api.com/account

### Errore SMTP Libero
- Verifica `LIBERO_EMAIL` e `LIBERO_PASSWORD` in `.env`
- Libero potrebbe richiedere verifica email prima di accettare SMTP
- Test: `./venv/bin/python execution/libero_notifier.py test-send`

### Dashboard non si avvia
- Verifica porta libera: `lsof -i :8080`
- Cambia porta in `execution/dashboard.py` o `winbet_config.json`

## Note Importanti

- **NON committare `.env`**: contiene credenziali sensibili
- **Il database `winbet.db` è opzionale**: viene rigenerato al primo scrape
- **venv/ è opzionale**: `./install.sh` lo ricrea se mancante
- **I log** vanno in `logs/` (auto-creata al primo avvio)
- **Budget The Odds API**: 500 crediti/mese free. 1 chiamata/giorno = ~60/mese

## Supporto

Per problemi o domande, vedi le SOP in `directives/` che spiegano nel dettaglio ogni componente.
