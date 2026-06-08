# Directive: Scraping Quote WinBet

## Obiettivo
Raccogliere, registrare e analizzare quote scommesse sportive da fonti:
- **SNAI** via API flutterseatech.it (TLS bypass curl_cffi)
- **Eurobet** via API detail-service (curl_cffi, quote in centesimi)
- **The Odds API** via REST v4 (multi-bookmaker globali, crediti: 500/mese)

## Input
- API key The Odds API: `$ODDS_API_KEY` (default in `--api-key`)
- Database: `winbet.db` (SQLite)
- Fonti: `--sources snai,eurobet,theodds`

## Script da Utilizzare

### Scraping manuale
```bash
cd /mnt/c/Users/angel/WinBet
python3 execution/scrape_unified_v2.py \
  --sources snai,eurobet,theodds \
  --api-key "YOUR_KEY" \
  --store-db \
  --output .tmp/winbet_unified_v2.json \
  --notify
```

### Scraping automatico via cronjob
```
* * * * *  →  Ogni minuto
0 * * * *  →  Ogni ora (attivo)
```
Job ID: `688e28232eb8` (orario), `49c82947c398` (no-agent script)

Intervallo configurato: 60 minuti (aggiornato da 30 min).

## Output
- `winbet.db` — SQLite con tabelle:
  - `matches` — partite (event_id, squadre, data)
  - `odds` — quote correnti (bookmaker, market, selection, odds)
  - `odds_history` — cronologia tutte le quote (per grafici trend)
  - `surebets` — surebets rilevate (profit_percent, timestamp)
  - `scrape_log` — log per esecuzioni
- JSON: `.tmp/winbet_unified_v2.json`
- Notifiche: file `.tmp/winbet_notifications.log`

## Struttura Quote

### SNAI
- API: `betting-snai.flutterseatech.it`
- Quote in centesimi (142 → 1.42)
- Mappa: `scommessaMap` + `infoAggiuntivaMap` + `esitoList`

### Eurobet
- API: `www.eurobet.it/detail-service/sport-schedule/services/...`
- Quote in centesimi (142 → 1.42)
- Mercati: `betGroupList → oddGroupList → oddList`

### The Odds API
- API: `api.the-odds-api.com/v4`
- Quote dirette in formato decimale
- Mercati: `h2h`, `totals`, `btts` (dove supportato)
- Region: `eu` (quote Europe)

## Surebet Detection
Rilevamento: `margin = sum(1/best_odds) < 1.0`
- Normalizzazione nomi squadra (accenti, spazi, sinonomi IT↔EN)
- Confronto quote tra fonti diverse
- Salvataggio in `surebets` con profitto calcolato

## Casi Limite
- **SNAI API down**: il cronjob riprova 1 volta dopo 2 min
- **Eurobet cambia endpoint**: aggiornare `EUROBET_ENDPOINTS` in `eurobet_api_scraper.py`
- **The Odds API rate limit**: 500 crediti/mese. Ogni chiamata = 1 credito per regione*mercato
- **Nessuna surebet**: normale, i mercati sono efficienti

## Troubleshooting
- `ImportError` → assicurarsi di essere nella directory `/mnt/c/Users/angel/WinBet`
- `curl_cffi` non trovato → `pip install curl_cffi`
- DB lock → SQLite è single-writer, evitare esecuzioni parallele
- SNAI ERR_HTTP2 → usare sempre `impersonate='chrome136'`
