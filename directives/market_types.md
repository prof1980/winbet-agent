# Direttiva — Tipologie di Quote (Market Types)

## Obiettivo
Definire le tipologie di quote calcistiche da raccogliere, registrare e analizzare.

## Quote di Base (sempre raccolte)
| Tipo | Nome | Descrizione |
|------|------|-------------|
| 1X2 | Esito Finale | 1 (casa), X (pareggio), 2 (trasferta) |
| DC | Doppia Chance | 1X, 12, X2 |

## Quote di Mercato Comune
| Tipo | Nome | Descrizione |
|------|------|-------------|
| OU25 | Under/Over 2.5 | Under 2.5, Over 2.5 |
| OU15 | Under/Over 1.5 | Under 1.5, Over 1.5 |
| OU35 | Under/Over 3.5 | Under 3.5, Over 3.5 |
| BTTS | Goal/No Goal | Entrambe segnano (GG) o meno (NG) |

## Quote Avanzate
| Tipo | Nome | Descrizione |
|------|------|-------------|
| H1X2 | Handicap 1 | Esito finale con handicap -1/+1 |
| HOU | Handicap Over/Under | Handicap asiatico o europeo |
| CS | Correct Score | Risultato esatto (es. 1-0, 2-1) |
| HTFT | 1° Tempo / Finale | Combinazioni esito primo tempo + finale |
| FIRST_GOAL | Primo Marcatore | Primo gol della partita |

## Quote a Margine Ridotto
| Tipo | Nome | Descrizione |
|------|------|-------------|
| DRAW_NO_BET | Draw No Bet | 1 o 2, rimborso su pareggio |

## Input
- Lista di market_type attivi (da filtrare dall'utente).

## Output
- Lista approvata scritta in `config/markets.json`.

## Casi limite
- Se un bookmaker non offre un mercato attivo, il campo `markets` dell'evento conterrà solo i mercati disponibili.
- Mercati con meno di 2 selection non sono registrati.
