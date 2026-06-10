# 📝 Changelog

Tutte le modifiche rilevanti al progetto WinBet sono documentate in questo file.

Il formato è basato su [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
e il progetto segue [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Aggiunto
- 🧩 **Cartella `skills/`** con 4 skill riusabili (bookmaker-odds-scraper, dedupe-matches-merge, libero-email-notifier, python-project-replication-package)
- 🔄 **Auto-sync workflow** (`scripts/winbet_sync_github.sh`) per tenere il repo GitHub aggiornato
- 📚 **`AUTO_SYNC.md`** con documentazione completa del workflow di sincronizzazione
- 🤖 **GitHub Actions CI** (`.github/workflows/ci.yml`) con lint, test import, structure check
- 📋 **`CHANGELOG.md`** per tracciare le modifiche

### Migliorato
- 🛡️ Verifica automatica assenza di secrets in CI
- 📖 Documentazione più completa (AUTO_SYNC, skills/README)

## [1.0.0] - 2026-06-08

### Aggiunto
- 🎰 Agente WinBet completo per scraping quote calcistiche multi-bookmaker
- 🕷️ **SNAI scraper** con TLS bypass via `curl_cffi` (chrome136 impersonation)
- 🕷️ **Eurobet scraper** per 79+ eventi (mondiali + amichevoli)
- 🌍 **The Odds API scraper** con rate limit intelligente (60 crediti/mese)
- 🔄 **Orchestratore unificato** (`scrape_unified_v2.py`) con normalizzazione cross-bookmaker
- 💰 **Surebet detection** cross-bookmaker con calcolo profitto
- 🗄️ **Database SQLite** con schema normalizzato (matches, odds, odds_history, surebets, scrape_log)
- 🔀 **Deduplica e merge partite** (`dedupe_matches.py`) con normalizzazione nomi squadre IT↔EN
- 📊 **Dashboard Flask** interattiva su 3 colonne (campionati, partite, analisi)
- 🎯 **Match cards collassabili** con tabelle bookmaker per mercato
- ⭐ **Evidenziazione quota migliore** per selezione
- 🧹 **Cleanup automatico** partite finite
- 📧 **Notifiche email Libero** (SMTP/IMAP) con:
  - Report giornaliero alle 8:00 a `angelo.bruno80@gmail.com`
  - Monitor IMAP ogni 10 min con parser comandi (status, surebet, matches, odds, stop, start, help)
- ⏰ **Cronjob automatici** (5 attivi):
  - `49c82947c398` — Scraping SNAI+Eurobet ogni 2h
  - `688e28232eb8` — Scraping SNAI+Eurobet (orario)
  - `e1e93f1bdc80` — The Odds API giornaliero alle 9:00
  - `0abd69074c12` — Email Monitor IMAP ogni 10 min
  - `d467f1410c8d` — Daily Report alle 8:00
- 🔒 **Sicurezza**: permessi 600 su `.env`, PAT GitHub in env var, `.gitignore` completo
- 📚 **SOP complete** in `directives/` (10 file Markdown)
- 📖 **README** professionale con badge, quick start, sezioni multiple
- 🐚 **Script di installazione** (`install.sh`) per setup automatico
- 🧪 **Requirements.txt** con versioni bloccate

### Modalità
- 🟢 **LIVE**: scraping reale ogni 2 ore (SNAI+Eurobet) + 1 volta/giorno (The Odds API)
- 🟡 **DEMO**: dati simulati per test pipeline

### Test
- ✅ SNAI: 10+ eventi, 374+ quote scrape reali
- ✅ Eurobet: 79+ eventi, 551+ quote scrape reali
- ✅ The Odds API: 72+ eventi mondiali
- ✅ Surebet detection: rilevate +0.17% (Germania vs Curacao) e altre
- ✅ Email: invio report + ricezione comandi verificata end-to-end
- ✅ Dashboard: tutte le leghe e bookmaker visibili
- ✅ Merge partite: 148 → 106 partite, 0 duplicati residui

### Crons attivi
- 5 cronjob schedulati e funzionanti

[Unreleased]: https://github.com/prof1980/winbet-agent/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/prof1980/winbet-agent/releases/tag/v1.0.0
