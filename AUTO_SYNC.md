# 🔄 Auto-Sync Workflow

Questo documento spiega come WinBet Agent si tiene sincronizzato con il repository GitHub quando:
- Viene aggiunta una nuova skill
- Viene migliorato uno script
- Viene aggiornata una SOP
- Viene fixato un bug critico

## Strategia

WinBet segue una **strategia di miglioramento continuo** (3 livelli, vedi [`directives/AGENTS.md`](../directives/AGENTS.md)):

1. **Direttive (Cosa fare)** — SOP in `directives/`
2. **Orchestrazione (Decisioni)** — L'AI agent decide quando migliorare
3. **Esecuzione (Lavoro)** — Script Python deterministici

Quando un componente viene migliorato, deve riflettersi in:
- Codice (`execution/`)
- Documentazione (`directives/`)
- Skills riusabili (`skills/`)
- Database (se schema cambia)

## Workflow di aggiornamento

### Trigger di aggiornamento

L'agente WinBet aggiorna il repo GitHub quando:

| Trigger | Esempio |
|---|---|
| Nuova skill creata | `~/.hermes/skills/winbet-newfeature/` aggiunta |
| Skill esistente migliorata | Pitfall nuovi scoperti durante test |
| Bug fix critico | Crash su scraper, race condition su DB |
| Nuova funzionalità | Aggiunta supporto nuovo bookmaker |
| Cambio architettura | Refactor orchestrator, cambio DB schema |
| Aggiornamento dipendenze | `requirements.txt` cambia (es. nuove versioni) |

### Procedura manuale

```bash
# 1. Verifica modifiche locali
cd /mnt/c/Users/angel/WinBet
git status

# 2. Copia i file nel repo
cp -r execution/* /tmp/winbet-repo/execution/
cp -r directives/* /tmp/winbet-repo/directives/
cp -r skills/* /tmp/winbet-repo/skills/ 2>/dev/null || true

# 3. Commit e push
cd /tmp/winbet-repo
git add -A
git commit -m "feat: descrizione modifiche"
git push origin main
```

### Procedura automatica (consigliata)

Crea un cronjob Hermes che esegue il sync periodico:

```bash
hermes cronjob create \
  --name "WinBet GitHub Auto-Sync" \
  --schedule "every 6h" \
  --no-agent \
  --script "winbet_sync_github.sh" \
  --workdir "/mnt/c/Users/angel/WinBet"
```

Lo script `winbet_sync_github.sh`:

```bash
#!/bin/bash
# Auto-sync WinBet -> GitHub
set -e

REPO_LOCAL="/tmp/winbet-repo"
SRC="/mnt/c/Users/angel/WinBet"

# 1. Copia sorgenti aggiornati
rsync -a --delete \
  --exclude='venv' --exclude='__pycache__' --exclude='logs' \
  --exclude='.tmp' --exclude='*.db' --exclude='*.log' \
  --exclude='*.pid' --exclude='*.zip' --exclude='.env' \
  --exclude='dashboard.html' \
  "$SRC/execution/" "$REPO_LOCAL/execution/"
rsync -a --delete "$SRC/directives/" "$REPO_LOCAL/directives/"
rsync -a --delete "$SRC/config/" "$REPO_LOCAL/config/"

# Copia skill rilevanti WinBet
for skill in bookmaker-odds-scraper dedupe-matches-merge \
            libero-email-notifier python-project-replication-package; do
  if [ -d "$HOME/.hermes/skills/$skill" ]; then
    rsync -a --delete "$HOME/.hermes/skills/$skill/" \
                   "$REPO_LOCAL/skills/$skill/"
  fi
done

# 2. Git add, commit, push (se ci sono modifiche)
cd "$REPO_LOCAL"
git add -A

if git diff --cached --quiet; then
  echo "Nessuna modifica da sincronizzare"
  exit 0
fi

git commit -m "chore: auto-sync $(date +%Y-%m-%d\ %H:%M)"

# Push usando il PAT da .env
GITHUB_PAT=$(grep "^GITHUB_PAT=" /mnt/c/Users/angel/WinBet/.env | cut -d= -f2)
git push https://x-access-token:${GITHUB_PAT}@github.com/prof1980/winbet-agent.git main
```

## File di configurazione `.syncrc.yml`

```yaml
# File di configurazione auto-sync
github:
  repo: prof1980/winbet-agent
  branch: main
  schedule: every 6h
  commit_message_template: "chore: auto-sync {date}"

sync_paths:
  - source: execution/
    destination: execution/
  - source: directives/
    destination: directives/
  - source: config/
    destination: config/
  - source: ~/.hermes/skills/bookmaker-odds-scraper/
    destination: skills/bookmaker-odds-scraper/
  - source: ~/.hermes/skills/dedupe-matches-merge/
    destination: skills/dedupe-matches-merge/
  - source: ~/.hermes/skills/libero-email-notifier/
    destination: skills/libero-email-notifier/
  - source: ~/.hermes/skills/python-project-replication-package/
    destination: skills/python-project-replication-package/

exclude_patterns:
  - venv/
  - __pycache__/
  - *.pyc
  - *.db
  - *.log
  - *.pid
  - *.zip
  - .env
  - dashboard.html
```

## Best practices

1. **Mai committare credenziali** — il `.gitignore` esclude `.env` automaticamente
2. **Testa prima di committare** — `git diff` per rivedere le modifiche
3. **Messaggi di commit descrittivi** — `feat:`, `fix:`, `docs:`, `chore:`, `refactor:`
4. **Una feature per commit** — meglio commit atomici
5. **Sync dopo test** — non committare se i test falliscono

## Troubleshooting

### "Authentication failed"
Verifica che `GITHUB_PAT` in `.env` sia ancora valido. I PAT scadono dopo 90 giorni (default). Per rigenerare: https://github.com/settings/tokens

### "Repository not found"
Verifica che il repo esista e tu abbia permessi di scrittura. Settings → Collaborators → aggiungi il bot

### "Conflict: remote contains work not in local"
Fai `git pull --rebase` prima di pushare, o usa `--force-with-lease` se hai la certezza che il remote non ha modifiche importanti

## Note

- Il sync automatico **non** è attivo di default (per evitare push indesiderati)
- Per attivarlo: `hermes cronjob create --name "WinBet Sync" --schedule "every 6h" --no-agent --script "winbet_sync_github.sh"`
- Per disattivarlo: `hermes cronjob pause <job_id>`
- Per controllare lo stato: `hermes cronjob list`
