# Direttiva: WinBet Scraping

## Obiettivo
Raccogliere quote scommesse da bookmaker italiani e internazionali, aggiornare il database WinBet e rilevare surebet.

## Strumenti
- `bookmaker-odds-scraper` skill (Hermes skill system)
- `execution/winbet_skill_bridge.py` — bridge tra skill e DB
- `execution/scraper.py` — scraper alternativo (DEMO / the-odds-api)

## Flusso Scraping (LIVE mode)
1. `winbet_scrape_cycle.sh` eseguito ogni ora dal cronjob `winbet-autoscraper`
2. Se mode=LIVE: `winbet_skill_bridge.py` chiama la skill `bookmaker_scraper.py`
3. Se mode=DEMO: `scraper.py` varia le quote simulate nel DB
4. Surebet detection: `surebet_detector.py` calcola arbitraggi
5. Notifiche: `notifications.py` invia alert su Telegram

## Configurazione Skill
La skill `bookmaker-odds-scraper` risiede in:
`~/.hermes/skills/bookmaker-odds-scraper/`

File:
- `scripts/bookmaker_scraper.py` — scraper engine multi-strategy
- `scripts/bookmakers.json` — configurazione 8 bookmaker
- `references/troubleshooting.md` — guida debug

## Comandi Skill Standalone
```bash
# Lista bookmaker
python3 ~/.hermes/skills/bookmaker-odds-scraper/scripts/bookmaker_scraper.py list-bookmakers --output /tmp/bm.json

# Scrape singolo bookmaker
python3 ~/.hermes/skills/bookmaker-odds-scraper/scripts/bookmaker_scraper.py scrape \
  --bookmaker snai --sport calcio --competition serie-a --output /tmp/snai.json

# Discovery (trova endpoint API)
python3 ~/.hermes/skills/bookmaker-odds-scraper/scripts/bookmaker_scraper.py discover \
  --bookmaker snai --sport calcio --output /tmp/discovery.json

# Compare multi-bookmaker
python3 ~/.hermes/skills/bookmaker-odds-scraper/scripts/bookmaker_scraper.py compare \
  --bookmakers snai,eurobet,oddsportal --sport calcio --competition serie-a --output /tmp/comp.json
```

## Passaggio DEMO → LIVE
1. Ottieni API key: https://the-odds-api.com (free tier: 500 req/mese)
2. Inserisci in `winbet_config.json`: `api_key_theoddsapi`
3. Cambia `mode` da `DEMO` a `LIVE`
4. Il cronjob userà automaticamente `winbet_skill_bridge.py` con la skill

## Casi Limite
- Bookmaker blocca (CAPTCHA): usare `--no-headless`, aumentare delays in `bookmakers.json`
- Nessun risultato: eseguire `discover` per aggiornare selettori
- IP bannato: attendere 30-60 min, usare rete diversa
- Bet365: usa WebSocket, failure rate più alto — considerare esclusione
