# Report Giornaliero WinBet

> Direttiva: generazione e invio automatico del report giornaliero sul funzionamento dell'agente WinBet.

## Obiettivo

Ogni mattina alle 8:00 (UTC) inviare un'email con un report completo sullo stato dell'agente:
- Salute del sistema
- Attività di scraping delle 24h precedenti
- Surebet rilevate più profittevoli
- Cronologia attività

## Destinatari

- **Default**: `angelo.bruno80@gmail.com`
- Modificabile con flag `--to` (accetta più destinatari separati da virgola)

## Componente

### `execution/winbet_daily_report.py`
Script Python che:
1. Legge statistiche da `winbet.db` (SQLite)
2. Calcola metriche di sistema (disco, dimensione DB)
3. Genera report in doppio formato: **plaintext** + **HTML**
4. Invia email via `LiberoNotifier` (SMTP)
5. Subject: `[WinBet] Report YYYY-MM-DD`

### Sezioni del report

| Sezione | Contenuto |
|---|---|
| **Stato Generale** | Partite, quote, surebet totali nel DB |
| **Stato Sistema** | DB size, disco libero, intervallo scraping, modalità |
| **Bookmaker Attivi** | Top 10 per numero partite raccolte |
| **Top Campionati** | Top 8 leghe con più partite |
| **Surebet** | Conteggi per fascia profitto (≥1%, ≥5%) + top 10 dettagliate |
| **Cronologia Scraping** | Ultimi 7 giorni per bookmaker (date, run, successi) |
| **Footer** | Link dashboard, info comandi email |

### Metriche chiave

- **Surebet profittevoli (≥1%)**: numero totale opportunità profittevoli
- **Surebet alta priorità (≥5%)**: numero opportunità molto profittevoli
- **Profitto massimo**: % profitto più alto rilevato
- **Quote aggiornate oggi**: nuove quote raccolte nelle ultime 24h
- **Run scraping OK**: numero scrape andati a buon fine

## Test manuale

```bash
# Dry-run (stampa a terminale senza inviare)
cd /mnt/c/Users/angel/WinBet
./venv/bin/python execution/winbet_daily_report.py --to angelo.bruno80@gmail.com --dry-run

# Invio reale
./venv/bin/python execution/winbet_daily_report.py --to angelo.bruno80@gmail.com

# Report settimanale (ultimi 7 giorni)
./venv/bin/python execution/winbet_daily_report.py --to angelo.bruno80@gmail.com --days 7

# Più destinatari
./venv/bin/python execution/winbet_daily_report.py \
  --to angelo.bruno80@gmail.com,watson.ag@libero.it
```

## Schedulazione automatica

### Cronjob Hermes

Creato il 5 Giugno 2026:

| Campo | Valore |
|---|---|
| Job ID | `d467f1410c8d` |
| Nome | WinBet Daily Report 8:00 |
| Schedule | `0 8 * * *` (ogni giorno alle 8:00 UTC) |
| Comando | `./venv/bin/python execution/winbet_daily_report.py --to angelo.bruno80@gmail.com` |
| Deliver | local |

### Modificare orario

```bash
# Esempio: sposta alle 7:30
hermes cronjob update d467f1410c8d --schedule "30 7 * * *"

# Esempio: ogni lunedì (report settimanale)
hermes cronjob update d467f1410c8d --prompt "Esegui: cd /mnt/c/Users/angel/WinBet && ./venv/bin/python execution/winbet_daily_report.py --to angelo.bruno80@gmail.com --days 7"
```

### Più report al giorno

```bash
# Aggiungi report pomeridiano alle 20:00
hermes cronjob create --name "WinBet Daily Report 20:00" --schedule "0 20 * * *" \
  --prompt "Esegui: cd /mnt/c/Users/angel/WinBet && ./venv/bin/python execution/winbet_daily_report.py --to angelo.bruno80@gmail.com"
```

## Formato email

Il destinatario riceve un'email con:
- **Versione HTML** (con CSS, tabelle stilizzate, badge colorati per profitto)
- **Versione plaintext** (per client email che non supportano HTML)
- **Subject**: `[WinBet] Report 2026-06-05`
- **Mittente**: `watson.ag@libero.it`

## Note di design

- **Sanitizzazione**: la password SMTP non viene mai inclusa nel report
- **Errori gracefully**: se il DB ha problemi, il report mostra "Database non trovato" ma non crasha
- **Soglie profitto**: parametri `--min-profit` configurabili (default 1%)
- **Compressione**: selezioni surebet limitate a top 3 per partita per leggibilità
- **Internazionalizzazione**: subject e header in italiano, formato data ISO 8601

## Troubleshooting

### Email non arriva a Gmail
- Controllare che `watson.ag@libero.it` non sia in spam per `angelo.bruno80@gmail.com`
- Gmail potrebbe classificare email Libero come "Promozioni": spostare in "Principale"
- Verificare invio: `tail -f ~/.hermes/logs/cronjob-d467f1410c8d.log` (path da verificare)

### Report mostra 0 partite
- Lo scraper potrebbe non aver girato. Verificare cronjob `49c82947c398` e `688e28232eb8`
- Eseguire scraping manuale: `python execution/scrape_unified_v2.py --sources snai,eurobet --store-db`

### Crash su `collect_db_stats`
- Schema DB cambiato: aggiornare le query nello script
- Controllare tabelle con: `sqlite3 winbet.db ".schema"`

## Metriche di successo

- ✅ Email recapitata ogni mattina alle 8:00
- ✅ Subject identifica chiaramente il giorno
- ✅ Top 10 surebet sempre visibili
- ✅ Stato scraping sempre aggiornato (run OK/falliti)
- ✅ Pronto per delivery anche in orari non lavorativi (cronjob automatico)
