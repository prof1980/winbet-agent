# Direttiva: WinBet Inizializzazione

## Obiettivo
Inizializzare il sistema WinBet con liste approvate dall'utente per: tipologie di quote, campionati di calcio, tipo di database, e bookmaker abilitati.

## Input
- Lista proposta dall'utente (da approvare/modificare)
- Scelta tecnica per database (SQLite raccomandato per semplicità)

## Output
- File config `winbet_config.json` con tutte le impostazioni approvate
- Database SQLite `winbet.db` creato e inizializzato
- Direttive di scraping aggiornate

## Liste Default

### Tipologie Quote Calcio
1. 1X2 (Esito Finale)
2. Under/Over 2.5
3. Under/Over 1.5
4. Under/Over 3.5
5. Gol/NoGol
6. Doppia Chance (1X, X2, 12)
7. Handicap Asiatico (-1, +1)
8. Corner Over/Under 9.5
9. Cartellini Over/Under 4.5
10. Esito 1° Tempo / 2° Tempo

### Campionati Default
1. Serie A (Italia)
2. Serie B (Italia)
3. Champions League
4. Europa League
5. Premier League (Inghilterra)
6. La Liga (Spagna)
7. Bundesliga (Germania)
8. Ligue 1 (Francia)

### Bookmaker Default
1. SNAI
2. Eurobet
3. Goldbet
4. William Hill
5. Sisal
6. Lottomatica
7. Bet365
8. OddsPortal (aggregator)

## Procedura
1. Chiedi approvazione/modifica delle liste
2. Scelta database (SQLite default)
3. Crea `winbet_config.json`
4. Crea `winbet.db` con schema completo
5. Carica dati demo se in modalità demo

## Casi Limite
- Se l'utente vuole aggiungere un campionato non previsto: aggiungere alla lista e aggiornare config
- Se l'utente vuole rimuovere una tipologia: cancellare dal config e dal database (drop columns se SQLite)
