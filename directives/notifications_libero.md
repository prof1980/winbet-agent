# Notifiche Email — Libero.it

> Direttiva: configurazione e uso del canale email `watson.ag@libero.it` per WinBet.

## Obiettivo

Inviare e ricevere email automatiche da/verso `watson.ag@libero.it` per:
1. **Report periodici** (orari/giornalieri) con stato scraping e surebet
2. **Alert surebet** quando viene rilevata un'opportunità profittevole
3. **Mini dashboard** in HTML allegato all'email
4. **Comandi remoti** via email (status, surebet, stop, start, ecc.)

## Architettura

```
┌─────────────────┐    SMTP     ┌──────────────────┐
│ WinBot scraper  │ ───────────▶│ smtp.libero.it   │
│ /scheduler      │ ◀───────────│ :465 SSL         │
└─────────────────┘    IMAP     └──────────────────┘
                                    │
                                    ▼
                              ┌──────────┐
                              │  Libero  │
                              │  Mailbox │
                              └──────────┘
                                    ▲
                                    │ IMAP polling
┌─────────────────┐    IMAP     ┌──────────────────┐
│ Email handler   │ ◀───────────│ imapmail.libero  │
│ (callback)      │              │ :993 SSL         │
└─────────────────┘              └──────────────────┘
```

## Componenti

### `execution/libero_notifier.py`
- Classe `LiberoNotifier` con metodi:
  - `send_email(to, subject, body, html_body=None, attachments=None)` — invio
  - `fetch_inbox(limit, unseen_only, since)` — lettura email
  - `mark_as_read(message_id)` — segna come letta
  - `search_emails(subject_pattern, from_pattern, since)` — ricerca
  - `monitor_inbox(callback, interval_seconds)` — loop continuo
- CLI: `test-send`, `test-fetch`, `monitor --interval N`

### `execution/winbet_email_handler.py`
- Classe `WinBetEmailHandler` con parser comandi
- Comandi supportati: status, surebet, matches, odds, stop, start, help
- Risponde automaticamente via SMTP
- CLI: `monitor --interval N`, `test`

## Configurazione `.env`

```bash
# === EMAIL LIBERO ===
LIBERO_EMAIL=watson.ag@libero.it
LIBERO_PASSWORD=***           # NON committare
LIBERO_SMTP_HOST=smtp.libero.it
LIBERO_SMTP_PORT=465
LIBERO_SMTP_SSL=true
LIBERO_IMAP_HOST=imapmail.libero.it
LIBERO_IMAP_PORT=993
```

⚠️ Il file `.env` ha permessi 600 (solo owner può leggerlo). Mai committare su git.

## Test iniziale

```bash
# Test invio (auto-risponde a se stesso)
./venv/bin/python execution/libero_notifier.py test-send

# Test ricezione (mostra ultime 5 email)
./venv/bin/python execution/libero_notifier.py test-fetch

# Test handler con comando fittizio "status"
./venv/bin/python execution/winbet_email_handler.py test
```

## Avvio monitor continuo

### Opzione A: processo standalone
```bash
./venv/bin/python execution/winbet_email_handler.py monitor --interval 120
```

### Opzione B: integrato nello scheduler
Lo scheduler esistente (`execution/scheduler.py`) può includere:
```python
from winbet_email_handler import WinBetEmailHandler
from threading import Thread

# Avvia monitor in thread daemon
handler = WinBetEmailHandler()
Thread(
    target=handler.notifier.monitor_inbox,
    args=(handler.handle,),
    kwargs={"interval_seconds": 120},
    daemon=True,
).start()
```

### Opzione C: cronjob separato
```bash
hermes cronjob create \
  --schedule "every 5m" \
  --name "WinBet Email Monitor" \
  --prompt "Esegui: cd /mnt/c/Users/angel/WinBet && ./venv/bin/python execution/winbet_email_handler.py monitor --interval 300"
```

## Comandi email supportati

L'utente invia email a `watson.ag@libero.it` con subject o body che inizi con:

| Comando | Esempio subject | Risposta |
|---|---|---|
| `status` | `[WinBet] status` | Report DB + scraper + bookmaker |
| `surebet` | `surebet` | Lista surebet attive >= 1% |
| `matches <lega>` | `matches serie a` | Partite di quella lega |
| `odds <squadra>` | `odds Inter` | Quote per quella squadra |
| `stop` | `stop` | Mette in pausa scraper |
| `start` | `start` | Riprende scraper |
| `help` | `help` | Lista comandi |

**Sicurezza**: solo email provenienti da mittenti in `allowed_senders` (default: solo l'email stessa) vengono elaborate. Tutte le altre vengono loggate e ignorate.

## Report periodici (da scheduler)

Modificare `execution/scheduler.py` per inviare, dopo ogni ciclo di scrape:

```python
from libero_notifier import LiberoNotifier

n = LiberoNotifier()
report = f"""
📊 WinBet Report Orario

Partite nel DB: {n_matches}
Surebet attive: {n_surebets}
Ultimo scrape: {last_scrape}
Bookmaker attivi: {n_bookmakers}

Dashboard: http://localhost:8080/
"""
n.send_email(
    to="watson.ag@libero.it",
    subject=f"[WinBet] Report {datetime.now():%Y-%m-%d %H:%M}",
    body=report,
    html_body=render_html_dashboard(),
)
```

## Troubleshooting

### Errore autenticazione SMTP
- Verificare che password in `.env` sia quella dell'account (no spazi/char strani)
- Libero potrebbe richiedere verifica email dopo cambiamenti password recenti
- Se hai 2FA attivo, potrebbe servire una password specifica

### IMAP restituisce lista vuota
- Verificare che la cartella sia "INBOX" (case-sensitive)
- Controllare che `unseen_only=False` se vuoi leggere anche le lette

### Email non arrivano
- Controllare spam
- Verificare log: `tail -f /var/log/mail.log` (lato server, non disponibile)
- Testare con `test-send` a se stesso

### Timeout connessione
- Libero può bloccare tentativi multipli ravvicinati
- Aumentare `interval_seconds` nel monitor
- Attendere 10-15 min se si sono fatti molti test

## Note di sicurezza

- La password è in chiaro nel `.env`: proteggere il file con `chmod 600`
- Non loggare MAI la password: usare `_sanitize()` prima di stampare
- Se si sospetta compromissione, cambiare password dal pannello Libero
- Il monitor IMAP potrebbe leggere email personali: usare un account dedicato a WinBet
- I comandi email sono limitati a mittenti autorizzati (whitelist)
