# Direttiva — Campionati di Calcio

## Obiettivo
Definire i campionati di calcio da monitorare per la raccolta quote.

## Fonte
Campionati principali disponibili sui bookmaker italiani e internazionali.

## Lista Proposta

### Top 5 Europee
| Key | Nome | Paese | Priorità |
|-----|------|-------|----------|
| serie-a | Serie A | Italia | Alta |
| premier-league | Premier League | Inghilterra | Alta |
| la-liga | La Liga | Spagna | Alta |
| bundesliga | Bundesliga | Germania | Alta |
| ligue-1 | Ligue 1 | Francia | Alta |

### Secondarie
| Key | Nome | Paese | Priorità |
|-----|------|-------|----------|
| serie-b | Serie B | Italia | Media |
| championship | EFL Championship | Inghilterra | Media |
| liga-portugal | Primeira Liga | Portogallo | Media |
| eredivisie | Eredivisie | Olanda | Media |
| jupiler-pro | Jupiler Pro League | Belgio | Bassa |
| super-league | Super League | Svizzera | Bassa |
| bundesliga-2 | 2. Bundesliga | Germania | Bassa |
| ligue-2 | Ligue 2 | Francia | Bassa |
| la-liga-2 | La Liga 2 | Spagna | Bassa |
| serie-c | Serie C | Italia | Bassa |

### Coppe Europee
| Key | Nome | Paese | Priorità |
|-----|------|-------|----------|
| champions-league | UEFA Champions League | Europa | Alta |
| europa-league | UEFA Europa League | Europa | Media |
| conference-league | UEFA Conference League | Europa | Media |

### Nazionali
| Key | Nome | Paese | Priorità |
|-----|------|-------|----------|
| world-cup | FIFA World Cup | Mondiale | Alta (stagionale) |
| euro | UEFA Euro | Europa | Alta (stagionale) |
| nations-league | UEFA Nations League | Europa | Media (stagionale) |
| copa-america | Copa América | Sudamerica | Media (stagionale) |

## Input
- Lista di competition key attive (filtrata dall'utente).

## Output
- Lista approvata scritta in `config/competitions.json`.

## Casi limite
- Competizioni stagionali (Mondiali, Europei) restituiranno 0 eventi fuori periodo.
- Competizioni di bassa priorità possono essere escluse per ridurre il carico di scraping.
