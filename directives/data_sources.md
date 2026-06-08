# Direttiva — Fonti Dati Quote (Aggiornata al 28 Maggio 2026)

## IP Attuale del Server
- **IP**: 93.66.97.147
- **ISP**: Fastweb SpA / Vodafone DSL
- **Tipo**: IP residenziale italiano ✅
- **Città**: Milano, Lombardia
- **Conclusione**: il problema NON È l'IP. Il blocco avviene a livello applicativo/TLS/HTTP.

## Fonte Primaria: The Odds API ⚠️ (Temporaneamente Offline)
- **Stato**: HTTP 401, `error_code: OUT_OF_USAGE_CREDITS`
- **Ripristino**: inizio giugno 2026
- **Script**: `execution/the_odds_api.py`

## Fonte Secondaria: Scraping Diretto Bookmaker 🔴 (Bloccato)

### SNAI — BLOCCATO a livello HTTP
| Test | Risultato |
|------|-----------|
| TLS handshake | ✅ OK (TLSv1.3) |
| HTTP GET / | 🔴 Timeout assoluto (0 byte risposta) |
| HTTP/2 | 🔴 ERR_HTTP2_PROTOCOL_ERROR |
| HTTP/1.1 | 🔴 Timeout 15s, 0 byte |
| Playwright headless | 🔴 Timeout 20s su domcontentloaded |
| IP residenziale | ✅ Sì, ma bloccato comunque |

**Diagnosi**: SNAI implementa un blocco a livello HTTP: dopo il TLS handshake riuscito, il server non risponde affatto alla richiesta HTTP GET. Tecnica nota: "TCP sinkhole" o "TLS termination + HTTP drop" per filtrare client non autorizzati.

**Cause possibili**:
- TLS fingerprinting: il client curl/httpx/Playwright genera un fingerprint TLS diverso da un browser Chrome reale
- Header HTTP mancanti (Accept-Language, Referer, Sec-CH-UA, ecc.)
- Cookie/sessione mancanti
- Cloudflare o WAF in modalità "strict", che richiede JS challenge prima di servire contenuti
- Il sito richiede un token anti-automation (es. __cf_bm, _cfduid)

### Eurobet — URL Struttura Cambiata
- Vecchio URL: `https://www.eurobet.it/scommesse-sportive/calcio` → 404
- HTTP 404 + redirect Cloudflare → URL effettivo sconosciuto
- Richiede reverse-engineering aggiornamento URL base

### OddsPortal/CentroQuote — Geo-redirect + JS Pesante
- Redirect a `www.centroquote.it` (94KB HTML)
- HTML statico non contiene odds → tutto renderizzato con JavaScript frontend
- Richiede Playwright con attesa + interazione (click, scroll) per caricare quote
- Nessuna API JSON rilevata nel traffic capture

## Fonte Terziaria: Demo Data Generator 🟢 (Fallback Attivo)
- **Script**: `execution/demo_data.py`
- **36 eventi**, **2519 odds**, **7 bookmaker simulati**
- Usato cron attualmente

## Prossimi Passi Raccomandati

### Opzione A: Ripristino Automatico a Giugno (consigliata)
- The Odds API ripristinerà i crediti a inizio giugno
- Lo scheduler proverà automaticamente ogni ora
- Zero costo, zero manutenzione

### Opzione B: Trovare Endpoint API Pubbliche Alternative
Alcune fonti note (da verificare):
- Flashscore API (api.flashscore.it o similar)
- Betfair Exchange API (richiede account)
- OddsAPI.io (alternativa freemium)
- Sportmonks, API-Football (richiedono key)
- open-source odds-aggregator su GitHub

### Opzione C: Reverse-Engineering SNAI/Eurobet
Richiede:
1. Aprire il sito da PC Windows con browser Chrome reale
2. DevTools → Network → filtrare XHR/Fetch
3. Identificare l'endpoint API interno che serve le quote JSON
4. Replicare esattamente headers, cookie, TLS fingerprint di Chrome
5. Usare quel endpoint direttamente (spesso è un file `.json` o endpoint REST sotto /api/)

Esperienza documentata: molti bookmaker servono quote tramite endpoint come:
- `https://api.snai.it/api/v1/events?sport=calcio`
- `https://www.eurobet.it/api/prematch/events`
- Accessibili solo con sessione valida + cookie anti-bot + TLS fingerprint esatto

### Opzione D: Scraping con Browser Chrome Reale su PC Utente
- Avviare Chrome sul PC utente
- Intercettare il traffico con estensione o proxy locale
- Salvare le risposte JSON delle API
- Importare manualmente in WinBet DB

## Costo/Benefizio

| Opzione | Sforzo | Costo | Legale | Affidabilità |
|---------|--------|-------|--------|-------------|
| A — Attendere giugno | Zero | Zero | ✅ | Alta |
| B — API alternative | Basso | Basso/Freemium | ✅ | Media |
| C — Reverse-engineering | Alto | Zero | ⚠️ ToS | Alta |
| D — Browser utente | Medio | Zero | ✅ | Alta |

## Azione Immediata Consigliata
1. Attendere inizio giugno per The Odds API (più stabile, più legale)
2. Nel frattempo, usare Demo Data Generator per sviluppo e test
3. Se urgente: aprire Eurobet/SNAI su PC utente con Chrome → DevTools → identificare endpoint API → condividerlo per integrazione

---

*Aggiornamento: l'IP è confermato residenziale italiano (93.66.97.147, Fastweb/Vodafone). Il blocco SNAI non è IP-based ma basato su TLS fingerprinting e/o challenge HTTP.*
