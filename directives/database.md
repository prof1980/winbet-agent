# Direttiva — Database Quote

## Obiettivo
Scegliere, creare e mantenere un database per la registrazione e l'aggiornamento delle quote raccolte.

## Opzioni Proposte

### Opzione A: SQLite (Locale, File-based)
- **Vantaggi**: Nessun server richiesto, file singolo `winbet.db`, integrazione Python nativa, zero configurazione.
- **Svantaggi**: Non condivisibile su più host, I/O su disco per scritture frequenti.
- **Uso consigliato**: Setup locale rapido, test, singolo utente.

### Opzione B: PostgreSQL (Server)
- **Vantaggi**: Concorrenza, JSONB per dati flessibili, robusto per produzione.
- **Svantaggi**: Richiede installazione server, configurazione utenti/password.
- **Uso consigliato**: Produzione multi-utente, integrazione con dashboard web.

## Schema Proposto (SQLite)

Tabella `events`:
| Colonna | Tipo | Descrizione |
|---------|------|-------------|
| id | INTEGER PK | ID evento interno |
| event_id | TEXT | ID bookmaker |
| home_team | TEXT | Squadra casa |
| away_team | TEXT | Squadra trasferta |
| start_time | TEXT | ISO 8601 |
| competition | TEXT | Campionato |
| league | TEXT | Lega normalizzata |
| scraped_at | TEXT | Timestamp raccolta |

Tabella `odds`:
| Colonna | Tipo | Descrizione |
|---------|------|-------------|
| id | INTEGER PK | ID odd |
| event_id | INTEGER FK | → events.id |
| bookmaker | TEXT | Nome bookmaker |
| market_type | TEXT | Tipo mercato (1X2, OU25, ecc.) |
| selection | TEXT | Esito (1, X, 2, Over, Under) |
| odds | REAL | Quota decimale |
| scraped_at | TEXT | Timestamp raccolta |

Tabella `odds_history`:
| Colonna | Tipo | Descrizione |
|---------|------|-------------|
| id | INTEGER PK | ID |
| event_id | INTEGER FK | → events.id |
| bookmaker | TEXT | Bookmaker |
| market_type | TEXT | Tipo mercato |
| selection | TEXT | Esito |
| odds_old | REAL | Quota precedente |
| odds_new | REAL | Quota nuova |
| change_pct | REAL | Variazione % |
| changed_at | TEXT | Timestamp cambio |

## Input
- Scelta del database (SQLite o PostgreSQL).
- Path del file DB (se SQLite) o stringa di connessione (se PostgreSQL).

## Output
- File `config/db_config.json` con la configurazione scelta.
- Database inizializzato con le tabelle sopra descritte.

## Casi limite
- Eventi senza `event_id` vengono identificati tramite hash `home_team|away_team|start_time`.
- Quote a 0.0 o < 1.01 non vengono inserite.
- Aggiornamenti ogni ora → SQLite WAL mode raccomandato per performance.
