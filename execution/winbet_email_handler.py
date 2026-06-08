#!/usr/bin/env python3
"""
WinBet Email Handler — Riceve email dall'utente e le parsa come comandi.

Modalità C: monitora automaticamente le risposte email dell'utente e,
se contengono comandi WinBet riconosciuti, aggiorna il DB o invia risposte.

Comandi supportati (subject o body):
- "status" → invia report stato scraping
- "surebet" → invia lista surebet attive
- "stop" → disattiva scraper
- "start" → riattiva scraper
- "matches <lega>" → invia partite di una lega (es. "matches serie a")
- "odds <squadra>" → invia quote per una squadra
- "help" → invia lista comandi

Configurazione: deve girare insieme a libero_notifier.monitor_inbox().

Esempio:
    from libero_notifier import LiberoNotifier
    from winbet_email_handler import WinBetEmailHandler
    handler = WinBetEmailHandler()
    n = LiberoNotifier()
    n.monitor_inbox(callback=handler.handle, interval_seconds=120)
"""
from __future__ import annotations

import logging
import os
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from libero_notifier import EmailMessage, LiberoNotifier

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DB_PATH = _PROJECT_ROOT / "winbet.db"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("winbet_email_handler")

PID_FILE = Path(__file__).resolve().parent / ".winbet_email_handler.pid"


class WinBetEmailHandler:
    """Gestisce le email ricevute dall'utente WinBet."""

    def __init__(self, allowed_senders: Optional[list[str]] = None) -> None:
        """
        Args:
            allowed_senders: lista email autorizzate a inviare comandi.
                             Se None, accetta solo dall'email del notifier stesso.
        """
        self.notifier = LiberoNotifier()
        self.allowed_senders = allowed_senders or [self.notifier.email]
        log.info(f"WinBetEmailHandler pronto (sender autorizzati: {self.allowed_senders})")

    def handle(self, msg: EmailMessage) -> None:
        """Entry point per monitor_inbox()."""
        log.info(f"Ricevuta email da {msg.from_addr}: {msg.subject}")

        # Filtra sender non autorizzati
        if msg.from_addr.lower() not in [s.lower() for s in self.allowed_senders]:
            log.warning(f"Sender non autorizzato: {msg.from_addr} — email ignorata")
            return

        # Identifica comando
        cmd = self._parse_command(msg)
        if not cmd:
            # Se è una risposta (RE:) o forward (FW:) e non contiene un comando
            # valido, ignora silenziosamente per evitare loop di auto-risposta.
            if re.search(r"^(re|fw|r|i|fwd):", msg.subject.strip().lower()):
                log.info(f"Nessun comando riconosciuto in email di risposta '{msg.subject}' — ignorata")
                return
            log.info(f"Nessun comando riconosciuto in '{msg.subject}' — rispondo con help")
            self._reply(msg, self._cmd_help())
            return

        # Dispatch
        action = cmd["action"]
        args = cmd["args"]
        log.info(f"Comando: {action} | args: {args}")

        try:
            if action == "status":
                response = self._cmd_status()
            elif action == "surebet":
                response = self._cmd_surebet()
            elif action == "matches":
                response = self._cmd_matches(args)
            elif action == "odds":
                response = self._cmd_odds(args)
            elif action == "stop":
                response = self._cmd_stop()
            elif action == "start":
                response = self._cmd_start()
            elif action == "help":
                response = self._cmd_help()
            else:
                response = f"❌ Comando sconosciuto: {action}\n\n{self._cmd_help()}"

            self._reply(msg, response)
        except Exception as e:
            log.error(f"Errore gestione comando {action}: {e}")
            self._reply(msg, f"❌ Errore: {e}")

    # -----------------------------------------------------------------------
    # Parsing comandi
    # -----------------------------------------------------------------------

    def _parse_command(self, msg: EmailMessage) -> Optional[dict]:
        """Estrae comando da subject o body."""
        # Cerca nel subject prima
        text = msg.subject or ""
        # Poi nel body se non trovato
        if msg.body:
            text += " " + msg.body[:200]

        text = text.lower().strip()

        # Rimuovi prefissi email comuni (RE:, FW:, R:, I:, FWD:) — ripetuti
        text = re.sub(r"^(re|fw|r|i|fwd):\s*", "", text)
        text = re.sub(r"^(re|fw|r|i|fwd):\s*", "", text)

        # Pattern: "[winbet] status" oppure "status" oppure "comando: status"
        text = re.sub(r"\[winbet\]\s*", "", text)
        text = re.sub(r"^(comando|cmd|command):\s*", "", text)

        # Match comandi
        if re.match(r"^(status|stato|report)\b", text):
            return {"action": "status", "args": ""}
        if re.match(r"^(surebet|arbitraggio|arb)\b", text):
            return {"action": "surebet", "args": ""}
        if re.match(r"^matches?\s+(.+)", text):
            args = re.match(r"^matches?\s+(.+)", text).group(1)
            return {"action": "matches", "args": args.strip()}
        if re.match(r"^odds?\s+(.+)", text):
            args = re.match(r"^odds?\s+(.+)", text).group(1)
            return {"action": "odds", "args": args.strip()}
        if re.match(r"^(stop|ferma|pausa)\b", text):
            return {"action": "stop", "args": ""}
        if re.match(r"^(start|riprendi|via)\b", text):
            return {"action": "start", "args": ""}
        if re.match(r"^(help|aiuto|comandi|\\?)\b", text):
            return {"action": "help", "args": ""}

        return None

    # -----------------------------------------------------------------------
    # Comandi
    # -----------------------------------------------------------------------

    def _cmd_status(self) -> str:
        """Report stato scraping + DB."""
        if not _DB_PATH.exists():
            return "❌ Database WinBet non trovato."

        conn = sqlite3.connect(_DB_PATH)
        c = conn.cursor()

        # Conteggi
        c.execute("SELECT COUNT(*) FROM matches")
        matches = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM odds")
        odds = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM surebets")
        surebets = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM scrape_log WHERE errors IS NULL OR errors = ''")
        scrapes_ok = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM scrape_log WHERE errors IS NOT NULL AND errors != ''")
        scrapes_fail = c.fetchone()[0]

        # Ultimo scrape per bookmaker
        c.execute("""
            SELECT bookmaker_id, MAX(completed_at) as last,
                   CASE WHEN errors IS NULL OR errors = '' THEN 1 ELSE 0 END as success
            FROM scrape_log
            GROUP BY bookmaker_id
            ORDER BY last DESC
        """)

        bm_status = []
        for bm, last, success in c.fetchall():
            status = "✅" if success else "❌"
            bm_status.append(f"  {status} {bm}: {last}")

        conn.close()

        text = f"""
📊 STATO WINBET

Database:
  • Partite: {matches}
  • Quote totali: {odds}
  • Surebet rilevate: {surebets}

Scraping:
  • Riusciti: {scrapes_ok}
  • Falliti: {scrapes_fail}

Bookmaker:
{chr(10).join(bm_status) if bm_status else '  (nessuno scrape registrato)'}

Aggiornato: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        """.strip()
        return text

    def _cmd_surebet(self) -> str:
        """Lista surebet attive con profitto >= 1%."""
        if not _DB_PATH.exists():
            return "❌ Database WinBet non trovato."

        conn = sqlite3.connect(_DB_PATH)
        c = conn.cursor()
        c.execute("""
            SELECT s.match_id, m.home_team, m.away_team, s.profit_percent,
                   s.selections, s.market_type
            FROM surebets s
            JOIN matches m ON s.match_id = m.match_id
            WHERE s.profit_percent >= 1.0
            ORDER BY s.profit_percent DESC
            LIMIT 20
        """)
        rows = c.fetchall()
        conn.close()

        if not rows:
            return "✅ Nessuna surebet attiva con profitto >= 1%"

        text = f"💰 SUREBET ATTIVE (profitto >= 1%)\n\n"
        for i, (mid, home, away, profit, sels_json, market) in enumerate(rows, 1):
            text += f"{i}. {home} vs {away}\n"
            text += f"   📊 Mercato: {market}\n"
            text += f"   💹 Profitto: {profit:.2f}%\n"
            # Parsa selections JSON
            try:
                import json
                sels = json.loads(sels_json) if sels_json else []
                for sel in sels:
                    bk = sel.get("bookmaker", "?")
                    oc = sel.get("label", sel.get("selection", sel.get("outcome", "?")))
                    od = sel.get("odds", 0)
                    text += f"   🎯 {oc} @ {od:.2f} ({bk})\n"
            except Exception:
                pass
            text += "\n"

        text += f"\nTotale: {len(rows)} surebet"
        return text

    def _cmd_matches(self, args: str) -> str:
        """Lista partite di una lega."""
        if not _DB_PATH.exists():
            return "❌ Database WinBet non trovato."

        conn = sqlite3.connect(_DB_PATH)
        c = conn.cursor()

        # Cerca lega per nome (LIKE case-insensitive) — usa league_id
        c.execute("""
            SELECT DISTINCT league_id
            FROM matches
            WHERE LOWER(league_id) LIKE ?
            LIMIT 1
        """, (f"%{args.lower()}%",))
        row = c.fetchone()

        if not row:
            conn.close()
            return f"❌ Lega '{args}' non trovata."

        league_id = row[0]
        league_name = league_id
        c.execute("""
            SELECT match_id, home_team, away_team, match_date, match_time
            FROM matches
            WHERE league_id = ?
            ORDER BY match_date, match_time
            LIMIT 50
        """, (league_id,))
        matches = c.fetchall()
        conn.close()

        if not matches:
            return f"⚠️ Lega '{league_name}' senza partite."

        text = f"⚽ PARTITE — {league_name}\n\n"
        for mid, home, away, date, time in matches:
            text += f"  • {date} {time}: {home} vs {away}\n"

        text += f"\nTotale: {len(matches)} partite"
        return text

    def _cmd_odds(self, args: str) -> str:
        """Quote per una squadra."""
        if not _DB_PATH.exists():
            return "❌ Database WinBet non trovato."

        conn = sqlite3.connect(_DB_PATH)
        c = conn.cursor()

        c.execute("""
            SELECT DISTINCT m.match_id, m.home_team, m.away_team, m.match_date
            FROM matches m
            WHERE LOWER(m.home_team) LIKE ? OR LOWER(m.away_team) LIKE ?
            LIMIT 5
        """, (f"%{args.lower()}%", f"%{args.lower()}%"))
        rows = c.fetchall()

        if not rows:
            conn.close()
            return f"❌ Nessuna partita trovata per '{args}'"

        text = f"💰 QUOTE — {args}\n\n"
        for mid, home, away, date in rows:
            text += f"⚽ {home} vs {away} ({date})\n"
            c.execute("""
                SELECT bookmaker_id, market_type, selection_label, odds_decimal
                FROM odds
                WHERE match_id = ? AND market_type = '1X2'
                ORDER BY bookmaker_id, selection_label
            """, (mid,))
            odds_rows = c.fetchall()
            for bk, mkt, oc, od in odds_rows:
                if od:
                    text += f"   {bk}: {oc} @ {od:.2f}\n"
            text += "\n"

        conn.close()
        return text.strip()

    def _cmd_stop(self) -> str:
        """Disattiva scraper (setta flag in DB)."""
        # Implementazione: scrive un file di flag o aggiorna tabella config
        flag_path = _PROJECT_ROOT / ".tmp" / "scraper_paused.flag"
        flag_path.parent.mkdir(parents=True, exist_ok=True)
        flag_path.write_text(datetime.now().isoformat())
        return "⏸️ Scraper WinBet in pausa. Usa 'start' per riprendere."

    def _cmd_start(self) -> str:
        """Riattiva scraper."""
        flag_path = _PROJECT_ROOT / ".tmp" / "scraper_paused.flag"
        if flag_path.exists():
            flag_path.unlink()
        return "▶️ Scraper WinBet riattivato."

    def _cmd_help(self) -> str:
        """Lista comandi disponibili."""
        return """
🤖 COMANDI WINBET (via email)

Invia una email a watson.ag@libero.it con subject o body che inizi con:

  status          → Report stato scraping + DB
  surebet         → Lista surebet attive (profitto >= 1%)
  matches <lega>  → Es. "matches serie a" → partite di quella lega
  odds <squadra>  → Es. "odds Inter" → quote per quella squadra
  stop            → Metti in pausa lo scraper
  start           → Riprendi lo scraper
  help            → Questo messaggio

Esempi subject:
  [WinBet] status
  matches champions
  odds Juventus

Le email devono essere inviate da un mittente autorizzato.
        """.strip()

    # -----------------------------------------------------------------------
    # Reply
    # -----------------------------------------------------------------------

    def _reply(self, original: EmailMessage, body: str) -> None:
        """Invia una risposta via email."""
        # Subject: RE: [WinBet] comando
        subj = original.subject or "WinBet"
        if not subj.lower().startswith("re:"):
            subj = f"RE: {subj}"

        # Limita lunghezza
        if len(body) > 8000:
            body = body[:7900] + "\n\n[...troncato...]"

        self.notifier.send_email(
            to=original.from_addr,
            subject=subj,
            body=body,
        )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="WinBet Email Handler")
    sub = parser.add_subparsers(dest="command")

    p_monitor = sub.add_parser("monitor", help="Avvia monitor con handler WinBet")
    p_monitor.add_argument("--interval", type=int, default=120, help="Intervallo polling (s)")

    p_test = sub.add_parser("test", help="Testa un singolo comando")

    args = parser.parse_args()

    if args.command == "monitor":
        handler = WinBetEmailHandler()
        handler.notifier.monitor_inbox(
            callback=handler.handle,
            interval_seconds=args.interval,
        )
    elif args.command == "test":
        handler = WinBetEmailHandler()
        test_msg = EmailMessage(
            from_addr=handler.notifier.email,
            to_addr=handler.notifier.email,
            subject="status",
            body="status",
        )
        handler.handle(test_msg)
    else:
        parser.print_help()


if __name__ == "__main__":
    # Always overwrite PID file (clean stale lock from crashes)
    try:
        PID_FILE.write_text(str(os.getpid()))
    except Exception as e:
        log.warning(f"Impossibile creare PID file: {e}")

    try:
        main()
    finally:
        try:
            PID_FILE.unlink(missing_ok=True)
        except OSError:
            pass
