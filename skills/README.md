# 🧩 Skills — Hermes Agent Skills

Questa cartella contiene le **skill riusabili** (procedural memory) sviluppate durante la creazione di WinBet, rese disponibili per l'intero ecosistema Hermes Agent.

## Skills incluse

| Skill | Descrizione | Quando usarla |
|---|---|---|
| [`bookmaker-odds-scraper`](./bookmaker-odds-scraper/) | Multi-strategy scraping per bookmaker (API interception, DOM parsing, WebSocket) | Qualsiasi scraping di siti bookmaker con anti-bot (SNAI, Eurobet, Bet365, Sisal, ecc.) |
| [`dedupe-matches-merge`](./dedupe-matches-merge/) | Fusione partite duplicate cross-bookmaker con normalizzazione nomi/leghe | Quando più fonti inseriscono stessa partita con match_id diversi (es. SNAI "Amichevoli Internazionali" vs Eurobet "Amichevoli Nazionali") |
| [`libero-email-notifier`](./libero-email-notifier/) | Pattern SMTP/IMAP per invio/ricezione email (Libero, Gmail, Outlook) | Per qualsiasi progetto che debba inviare/ricevere email come canale di notifica/comando |
| [`python-project-replication-package`](./python-project-replication-package/) | Crea ZIP replicabile di un progetto Python con setup automatico | Quando vuoi distribuire il progetto per replica su altri sistemi |

## Formato skill

Ogni skill è una cartella con:
```
skill-name/
└── SKILL.md    # file markdown con descrizione, setup, esempi
```

Alcune skill hanno anche:
- `references/` — file di documentazione aggiuntiva
- `scripts/` — script helper
- `assets/` — template e configurazioni

## Installazione in altri progetti

```bash
# Copia la skill in ~/.hermes/skills/
cp -r skills/bookmaker-odds-scraper ~/.hermes/skills/

# Poi riavvia Hermes per ricaricare
```

## Auto-sync con GitHub

Le skill vengono sincronizzate automaticamente con il repository WinBet ad ogni miglioramento. Vedi [`AUTO_SYNC.md`](../AUTO_SYNC.md) per i dettagli del workflow.

## Contribuire

Per aggiungere una nuova skill:
1. Crea `skills/<nome-skill>/SKILL.md` con frontmatter YAML
2. Aggiungi descrizione e trigger conditions
3. Includi pitfalls e best practices
4. Testa con Hermes Agent
5. Apri una PR

Vedi [CONTRIBUTING.md](../CONTRIBUTING.md) per il workflow completo.
