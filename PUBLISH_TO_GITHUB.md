# 🚀 Istruzioni: Pubblica WinBet su GitHub

Il repository locale WinBet è pronto in `/tmp/winbet-repo` con **79 file, 530 KB, 1 commit iniziale**.

Per pubblicarlo su GitHub, segui una di queste procedure.

---

## Opzione 1: Tramite Web (più semplice)

### Passo 1: Crea il repository su GitHub
1. Vai su https://github.com/new
2. **Owner**: il tuo account (es. `angelobruno80`)
3. **Repository name**: `winbet-agent`
4. **Description**: `Agente autonomo per raccolta quote scommesse calcistiche, surebet detection e dashboard interattiva`
5. Seleziona **Public** (o Private se preferisci)
6. **NON** inizializzare con README/.gitignore (li abbiamo già)
7. Clicca **Create repository**

### Passo 2: Push del repository locale
GitHub ti mostrerà i comandi, ma questi sono quelli pronti:

```bash
cd /tmp/winbet-repo

# Aggiungi remote (sostituisci USERNAME con il tuo)
git remote add origin https://github.com/USERNAME/winbet-agent.git

# Verifica
git remote -v

# Push del branch main
git branch -M main
git push -u origin main
```

Se ti chiede autenticazione:
- **Username**: il tuo username GitHub
- **Password**: il tuo Personal Access Token (NON la password)

### Passo 3: Genera un Personal Access Token (se non ce l'hai)
1. https://github.com/settings/tokens
2. **Generate new token (classic)**
3. Scopes: `repo` (full), `workflow`
4. Copia il token (mai più visibile)
5. Usalo come password al push

---

## Opzione 2: Tramite GitHub CLI (più veloce)

### Installazione `gh` CLI (WSL/Ubuntu)
```bash
# Ubuntu/Debian
sudo apt update && sudo apt install gh

# macOS
brew install gh

# Windows
winget install GitHub.cli
```

### Login e creazione
```bash
# Login (si aprirà il browser)
gh auth login

# Crea repo pubblico e pusha in un comando
cd /tmp/winbet-repo
gh repo create winbet-agent --public \
  --description "Agente autonomo per raccolta quote scommesse calcistiche, surebet detection e dashboard interattiva" \
  --source=. --remote=origin --push
```

### Oppure se vuoi un repo privato
```bash
gh repo create winbet-agent --private \
  --description "..." \
  --source=. --remote=origin --push
```

---

## Opzione 3: Tramite SSH (se hai già le chiavi)

```bash
cd /tmp/winbet-repo
git remote add origin git@github.com:USERNAME/winbet-agent.git
git push -u origin main
```

---

## ✅ Verifica post-push

Dopo il push, vai su https://github.com/USERNAME/winbet-agent e verifica:

- [ ] README.md visibile nella homepage
- [ ] 79 file presenti
- [ ] Nessun `.env`, `winbet.db`, `venv/` o `__pycache__/` committato
- [ ] LICENSE presente
- [ ] Lingua del repo riconosciuta: Python

---

## 🔒 Note di sicurezza

⚠️ Il `.gitignore` esclude automaticamente:
- `.env` (credenziali)
- `winbet.db` (database)
- `venv/` (ambiente virtuale)
- `*.log`, `*.pid` (runtime)
- `__pycache__/` (cache Python)

**Verifica finale** prima del push:
```bash
cd /tmp/winbet-repo
git status
# NON deve mostrare .env, winbet.db, venv/
```

---

## 📋 Comandi riassuntivi

Se hai già `gh` installato e autenticato, **un solo comando basta**:

```bash
cd /tmp/winbet-repo && \
gh repo create winbet-agent --public \
  --description "Agente autonomo quote scommesse" \
  --source=. --remote=origin --push
```

---

## 🆘 Troubleshooting

### "Authentication failed"
- Verifica username corretto
- Usa PAT (non password) — https://github.com/settings/tokens
- Prova `gh auth login` se hai `gh` installato

### "Repository not found"
- Verifica URL: `https://github.com/USERNAME/winbet-agent.git`
- Verifica che il repo esista su GitHub
- Controlla ownership (non puoi pushare su repo altrui senza permessi)

### "Permission denied (publickey)"
- Configura SSH key: https://github.com/settings/keys
- Oppure passa a HTTPS con PAT

### File sensibili già committati
Se per errore hai committato `.env` o `winbet.db`:
```bash
# Rimuovi dal tracking (ma lasciali su disco)
git rm --cached .env winbet.db
git commit -m "chore: rimuovi file sensibili dal tracking"
```

⚠️ Se hai pushato secrets su GitHub, **ROTAZionali immediatamente**:
- Password Libero, Telegram token, The Odds API key
- Rigenera da pannello provider
- I secrets sono recuperabili anche dopo la rimozione dalla history git
