# Direttiva: Scraping Quote SNAI

## Obiettivo
Raccogliere quote calcistiche reali da SNAI tramite API flutterseatech.it ogni ora.

## Fonte Dati
- **Bookmaker**: SNAI (snai.it)
- **Endpoint API**: `https://betting-snai.flutterseatech.it/api/lettura-palinsesto-sport/palinsesto/prematch/v1/top-match?offerId=0`
- **Metodo**: GET con header `Referer`, `Origin`, `bet-locale`, `bet-brand`, `user_data`
- **Libreria**: `curl_cffi` con TLS impersonation (`chrome136`)

## Header Richiesti
```
Referer: https://www.snai.it/
Origin: https://www.snai.it
bet-locale: it_IT
bet-brand: 391
bet-offer: 0
user_data: {"accountId": null, "token": null, "tokenJWT": null, "locale": "it_IT", "loggedIn": false, "channel": 62, "brandId": 391, "offerId": 0, "clientType": "WEB"}
Accept: application/json
```

## Formato Dati
- **disciplinaList**: lista discipline (Calcio=1, Tennis=3, Basket=2, Rugby=12)
- **avvenimentoFeList**: eventi (partite) con codicePalinsesto + codiceAvvenimento
- **scommessaMap**: mercati disponibili per ogni evento
- **infoAggiuntivaMap**: quote per ogni esito (quota in centesimi → dividere per 100)

### Mappatura Mercati
| Codice Scommessa | Descrizione | Market Type |
|---|---|---|
| 3 | 1X2 ESITO FINALE | 1x2 |
| 18 | GOAL/NOGOAL | gol_nogol |
| 28319 | DOPPIA CHANCE MULTIESITI | doppia_chance |
| Altri | Over/Under, Pari/Dispari, ecc. | over_under, pari_dispari, ecc. |

## Quote
- Valori in **centesimi** (es. 108 = quota 1.08, 1000 = quota 10.00)
- Conversione: `quota_decimale = quota_raw / 100.0`

## Script Esecuzione
- **Path**: `execution/scrape_unified.py`
- **Subcommand**: `python3 scrape_unified.py --bookmakers snai --store-db`

## Casi Limite
1. **IP bannato**: curl_cffi risolve con TLS impersonation
2. **Sessione scaduta**: header `user_data` contiene token=null (utente non loggato)
3. **Nessun evento calcio**: in estate, Serie A è finita → amichevoli nazionali e mondiali
4. **Rate limiting**: attesa implicita tra chiamate, non superare 1 req/min

## Stagionalità
- **Stagione calcistica** (Set-Mag): Serie A, Serie B, Champions League
- **Estate** (Giu-Ago): Amichevoli nazionali, Mondiali, Qualificazioni Euro
- **Sempre disponibile**: Tennis, Basket (NBA, Eurolega)

## Note
- L'endpoint è NON documentato e potrebbe cambiare
- Se fallisce, verificare se SNAI ha cambiato dominio o path API
- `flutterseatech.it` è il backend di SNAI per le scommesse sportive
