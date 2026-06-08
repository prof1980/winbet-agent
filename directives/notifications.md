# Direttiva — Notifiche e Canali

## Obiettivo
Definire i canali per inviare report, mini-dashboard e alert all'utente.

## Canali Supportati
| Canale | Stato | Configurazione |
|--------|-------|----------------|
| Telegram | ✅ Pronto | Bot token + chat_id in `.env` |
| WhatsApp | ⚠️ Richiede API business | Non configurato |
| Email (SMTP) | ✅ Pronto | Server SMTP in `.env` |
| Console/Log | ✅ Sempre attivo | File `.tmp/notifications.log` |

## File di Configurazione
- `.env` nella root del progetto con:
  ```bash
  # Telegram
  TELEGRAM_BOT_TOKEN=your_bot_token_here
  TELEGRAM_CHAT_ID=your_chat_id_here

  # Email (opzionale)
  SMTP_HOST=smtp.gmail.com
  SMTP_PORT=587
  SMTP_USER=your_email@gmail.com
  SMTP_PASS=your_app_password
  SMTP_TO=destination@email.com
  ```

## Tipi di Notifica
1. **Report orario** — Riassunto scraping: eventi raccolti, quote aggiornate, sure bet rilevate.
2. **Mini-dashboard** — Tabella ASCII/HTML delle partite principali con quote migliori.
3. **Alert quote** — Quando una quota cambia > 10% rispetto alla media o alla precedente raccolta.
4. **Alert sure bet** — Nuova opportunità di arbitraggio rilevata.

## Script di Invio
- `execution/notify.py` — Wrapper che invia su tutti i canali configurati.

## Input
- Tipo di notifica (report, alert, dashboard).
- Payload JSON da includere.

## Output
- Stato invio per ogni canale.

## Casi limite
- Se Telegram non è configurato, la notifica viene solo loggata.
- Se l'invio fallisce, viene ritentato 1 volta dopo 30 secondi.
