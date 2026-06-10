# 📚 Documentazione aggiuntiva

Questa cartella contiene file di esempio e documentazione che non sono attivi nel repo
ma sono utili come riferimento.

## `ci-workflow-example.yml`

Esempio di GitHub Action per CI (lint, test import, verifica struttura).

**Per attivarlo**:
1. Vai su https://github.com/settings/tokens
2. Rigenera il PAT aggiungendo lo scope `workflow`
3. Aggiorna il PAT nel file `.env` di WinBet
4. Copia `ci-workflow-example.yml` in `.github/workflows/ci.yml`
5. Push: il prossimo commit attiverà automaticamente la CI

**Alternativa manuale** (senza scope `workflow`):
1. Vai su GitHub.com → repository → Settings → Secrets and variables → Actions
2. Crea un nuovo secret `GITHUB_TOKEN` con valore il tuo PAT (con scope workflow)
3. Aggiungi `.github/workflows/ci.yml` via web (drag & drop o web editor)
4. Le action gireranno con i permessi del PAT, non del GITHUB_TOKEN automatico
