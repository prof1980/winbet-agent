# Contributing to WinBet

Grazie per l'interesse a contribuire a WinBet! 🎉

## Setup sviluppo

```bash
git clone https://github.com/<your-username>/winbet-agent.git
cd winbet-agent
./install.sh
cp .env.example .env
nano .env  # inserisci le tue credenziali
```

## Workflow

1. Crea un branch per la feature: `git checkout -b feature/nome-feature`
2. Fai le modifiche e testa localmente
3. Commit con messaggio descrittivo: `git commit -m "feat: aggiungi supporto Sisal scraper"`
4. Push: `git push origin feature/nome-feature`
5. Apri una Pull Request

## Convenzioni

- **Python**: PEP 8, type hints dove possibile
- **SOP**: aggiungi/aggiorna file in `directives/` quando aggiungi nuove funzionalità
- **Test**: prima del PR, testa manualmente lo scraper e la dashboard
- **Credenziali**: MAI committare `.env` o qualsiasi PAT/key
- **Commit messages**: usa prefisso `feat:`, `fix:`, `docs:`, `chore:`, ecc.

## Struttura modifiche

### Aggiungere un nuovo bookmaker
1. Aggiungi scraper in `execution/scraper_<name>.py`
2. Aggiungi mapping in `execution/scrape_unified_v2.py`
3. Aggiungi entry in `config/bookmakers.json`
4. Aggiungi SOP in `directives/scrape_<name>.md`
5. Testa con `--sources <name>`

### Aggiungere un nuovo tipo di scommessa
1. Aggiungi normalizzazione in `execution/dedupe_matches.py` (MARKET_NORMALIZE)
2. Aggiorna dashboard template se serve UI specifica
3. Documenta in `directives/market_types.md`

## Segnalazione bug

Apri una Issue con:
- Descrizione del problema
- Steps per riprodurlo
- Output/Log rilevanti
- Ambiente (OS, Python version, ecc.)

## Sicurezza

⚠️ **NON aprire issue pubbliche per vulnerabilità di sicurezza!** Contatta i maintainer privatamente.
