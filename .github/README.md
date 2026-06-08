# 📊 Report giornaliero

Questo workflow invia automaticamente il report giornaliero WinBet.

## Setup

1. Crea un Personal Access Token su https://github.com/settings/tokens
2. Aggiungi i secrets al repository: Settings → Secrets and variables → Actions
   - `DAILY_REPORT_TO`: indirizzo email destinatario
3. Il workflow parte automaticamente ogni giorno alle 8:00 UTC

## Note

Questo è solo un esempio/template. L'esecuzione reale richiede accesso al
server WinBet con credenziali e dipendenze installate.
