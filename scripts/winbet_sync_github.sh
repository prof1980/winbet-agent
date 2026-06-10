#!/bin/bash
# WinBet Auto-Sync -> GitHub
# Sincronizza i file locali WinBet con il repository GitHub
# Schedulato oppure eseguibile manualmente
set -e

REPO_LOCAL="${WINBET_REPO_PATH:-/tmp/winbet-repo}"
SRC="${WINBET_SRC_PATH:-/mnt/c/Users/angel/WinBet}"
ENV_FILE="$SRC/.env"
LOG_FILE="$SRC/.tmp/sync.log"

mkdir -p "$(dirname "$LOG_FILE")"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

if [ ! -f "$ENV_FILE" ]; then
    log "❌ ERRORE: $ENV_FILE non trovato"
    exit 1
fi

GITHUB_PAT=$(grep "^GITHUB_PAT=" "$ENV_FILE" | cut -d= -f2 | tr -d '\n\r')
if [ -z "$GITHUB_PAT" ]; then
    log "❌ ERRORE: GITHUB_PAT non trovato in $ENV_FILE"
    exit 1
fi

if [ ! -d "$REPO_LOCAL/.git" ]; then
    log "❌ ERRORE: $REPO_LOCAL non è un repository git"
    exit 1
fi

log "🔄 Avvio sync: $SRC -> $REPO_LOCAL"

# 1. Copia sorgenti aggiornati (escludendo venv, db, log, secrets)
log "📁 Sincronizzazione execution/"
rsync -a --delete \
    --exclude='venv/' --exclude='__pycache__/' \
    --exclude='*.pyc' --exclude='*.db' --exclude='*.log' \
    --exclude='*.pid' --exclude='*.zip' \
    --exclude='.env' --exclude='dashboard.html' \
    "$SRC/execution/" "$REPO_LOCAL/execution/"

log "📁 Sincronizzazione directives/"
rsync -a --delete "$SRC/directives/" "$REPO_LOCAL/directives/" 2>/dev/null || true

log "📁 Sincronizzazione config/"
rsync -a --delete "$SRC/config/" "$REPO_LOCAL/config/" 2>/dev/null || true

log "📁 Sincronizzazione scripts/"
rsync -a --delete "$SRC/scripts/" "$REPO_LOCAL/scripts/" 2>/dev/null || true

log "🧩 Sincronizzazione skills rilevanti..."
for skill in bookmaker-odds-scraper dedupe-matches-merge \
            libero-email-notifier python-project-replication-package; do
    if [ -d "$HOME/.hermes/skills/$skill" ]; then
        rsync -a --delete "$HOME/.hermes/skills/$skill/" \
                       "$REPO_LOCAL/skills/$skill/"
        log "  ✅ $skill"
    else
        log "  ⚠️  $skill non trovata in ~/.hermes/skills/"
    fi
done

# 2. Git add + commit + push
cd "$REPO_LOCAL"
log "📝 Git: controllo modifiche..."

# Configura git se non già fatto
git config user.name "WinBet Auto-Sync" 2>/dev/null || true
git config user.email "winbet-sync@localhost" 2>/dev/null || true

git add -A

if git diff --cached --quiet; then
    log "✅ Nessuna modifica da sincronizzare"
    exit 0
fi

CHANGED=$(git diff --cached --name-only | wc -l)
log "📊 $CHANGED file modificati da committare"

COMMIT_MSG="chore: auto-sync $(date '+%Y-%m-%d %H:%M:%S')"
git commit -m "$COMMIT_MSG" -m "File modificati: $CHANGED" -m "Trigger: scheduled sync"

# 3. Push via HTTPS con PAT
log "📤 Push in corso..."
export GIT_ASKPASS="/bin/echo"
export GIT_TERMINAL_PROMPT="0"

PUSH_URL="https://x-access-token:***@github.com/prof1980/winbet-agent.git"
if git push "$PUSH_URL" main 2>&1 | tee -a "$LOG_FILE"; then
    log "✅ Push completato: https://github.com/prof1980/winbet-agent"
    exit 0
else
    log "❌ Push fallito"
    exit 1
fi
