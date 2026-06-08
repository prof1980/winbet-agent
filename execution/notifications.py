#!/usr/bin/env python3
"""WinBet Notification System — Invio notifiche via Hermes channels.

Utilizza `hermes send` CLI per inviare messaggi sui canali configurati
(Telegram, Discord, Slack) senza duplicare token API.

Requisito: `hermes` CLI in PATH.
"""

import sqlite3
import json
import subprocess
from datetime import datetime
from pathlib import Path

DB_PATH = "/mnt/c/Users/angel/WinBet/winbet.db"

def log_notification(type_: str, message: str, channel: str, status: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        INSERT INTO notifications (type, message, channel, status, sent_at)
        VALUES (?, ?, ?, ?, ?)
    """, (type_, message, channel, status, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def send_hermes_message(message: str, channel: str = "telegram") -> bool:
    """Invia messaggio via hermes CLI send."""
    try:
        result = subprocess.run(
            ["hermes", "send", message],
            capture_output=True, text=True, timeout=30
        )
        success = result.returncode == 0
        if not success:
            print(f"⚠️  hermes send failed: {result.stderr[:200]}")
        return success
    except Exception as e:
        print(f"⚠️  hermes send error: {e}")
        return False

def notify_surebets(new_only: bool = True):
    """Invia notifiche per surebet nuove o attive."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    if new_only:
        c.execute("""
            SELECT s.*, m.home_team, m.away_team, m.match_date, m.match_time
            FROM surebets s
            JOIN matches m ON s.match_id = m.match_id
            WHERE s.notified = 0 AND s.status = 'active'
            ORDER BY s.profit_percent DESC
        """)
    else:
        c.execute("""
            SELECT s.*, m.home_team, m.away_team, m.match_date, m.match_time
            FROM surebets s
            JOIN matches m ON s.match_id = m.match_id
            WHERE s.status = 'active'
            ORDER BY s.profit_percent DESC
        """)
    
    rows = c.fetchall()
    if not rows:
        print("🔕 Nessuna surebet da notificare.")
        return
    
    for row in rows:
        selections = json.loads(row["selections"])
        sel_text = " | ".join(
            f"{s['bookmaker']}: {s['selection']} @ {s['odds']:.2f}"
            for s in selections
        )
        
        msg = f"""🎯 WINBET SUREBET TROVATA!

⚽ {row['home_team']} vs {row['away_team']}
📅 {row['match_date']} {row['match_time']}
📊 Mercato: {row['market_type'].upper()}
💰 Profitto garantito: +{row['profit_percent']:.2f}%

🏦 Quote:
{sel_text}

⚡ Agisci prima che cambino!"""
        
        success = send_hermes_message(msg)
        status = "sent" if success else "failed"
        log_notification("surebet", msg, "telegram", status)
        
        # Marca come notificata
        c.execute("UPDATE surebets SET notified = 1 WHERE id = ?", (row["id"],))
    
    conn.commit()
    conn.close()
    print(f"📤 Surebet notificate: {len(rows)} (nuove: {new_only})")

def notify_odds_change(match_id: str = None, threshold: float = 0.15):
    """Notifica variazioni significative di quote."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    # Confronta quote attuali con media degli ultimi 3 campionamenti
    c.execute("""
        SELECT o.match_id, o.bookmaker_id, o.market_type, o.selection_name, 
               o.odds_value as current,
               AVG(h.odds_value) as avg_recent,
               m.home_team, m.away_team
        FROM odds o
        JOIN odds_history h ON o.match_id = h.match_id AND o.bookmaker_id = h.bookmaker_id
                           AND o.market_type = h.market_type AND o.selection_name = h.selection_name
        JOIN matches m ON o.match_id = m.match_id
        WHERE h.recorded_at > datetime('now', '-2 hours')
        GROUP BY o.match_id, o.bookmaker_id, o.market_type, o.selection_name
        HAVING ABS(o.odds_value - AVG(h.odds_value)) / AVG(h.odds_value) > ?
    """, (threshold,))
    
    rows = c.fetchall()
    for row in rows:
        change = (row["current"] - row["avg_recent"]) / row["avg_recent"] * 100
        direction = "📈" if change > 0 else "📉"
        
        msg = f"""{direction} VARIAZIONE QUOTA WINBET

⚽ {row['home_team']} vs {row['away_team']}
🏦 {row['bookmaker_id'].upper()} — {row['market_type'].upper()} {row['selection_name']}
💰 {row['avg_recent']:.2f} → {row['current']:.2f} ({change:+.1f}%)

🔗 Controlla nel dashboard!"""
        
        success = send_hermes_message(msg)
        log_notification("odds_change", msg, "telegram", "sent" if success else "failed")
    
    conn.close()
    print(f"📤 Variazioni quote notificate: {len(rows)}")

def send_mini_dashboard():
    """Invia un mini riepilogo dei campionati e partite di oggi."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    today = datetime.now().strftime("%Y-%m-%d")
    
    c.execute("SELECT COUNT(*) FROM matches WHERE match_date = ?", (today,))
    today_matches = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM surebets WHERE status = 'active'")
    active_surebets = c.fetchone()[0]
    
    c.execute("""
        SELECT league_id, COUNT(*) as cnt 
        FROM matches 
        WHERE match_date = ? AND status = 'scheduled'
        GROUP BY league_id
    """, (today,))
    
    league_lines = []
    for row in c.fetchall():
        league_lines.append(f"   • {row['league_id']}: {row['cnt']} partite")
    
    msg = f"""📊 WINBET MINI DASHBOARD

📅 Oggi: {today_matches} partite in programma
🎯 Surebet attive: {active_surebets}

🏆 Campionati:
{chr(10).join(league_lines) if league_lines else '   Nessuna partita oggi'}

⚡ WinBet monitoring attivo!"""
    
    success = send_hermes_message(msg)
    log_notification("mini_dashboard", msg, "telegram", "sent" if success else "failed")
    conn.close()
    print(f"📤 Mini dashboard inviata: {'OK' if success else 'FALLITO'}")

def send_report(report_type: str = "full"):
    """Invia un report completo di sistema."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    c.execute("SELECT COUNT(*) FROM matches"); total_matches = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM odds"); total_odds = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM surebets WHERE status='active'"); active_sure = c.fetchone()[0]
    c.execute("SELECT MAX(updated_at) FROM odds"); last_update = c.fetchone()[0]
    
    msg = f"""📋 WINBET REPORT

📊 Statistiche database:
   • Partite totali: {total_matches}
   • Quote totali: {total_odds}
   • Surebet attive: {active_sure}
   • Ultimo aggiornamento: {last_update or 'N/A'}

🔄 Scraping: ogni ora
📈 Surebet threshold: ≥1.0% profitto

WinBet operativo!"""
    
    success = send_hermes_message(msg)
    log_notification(f"report_{report_type}", msg, "telegram", "sent" if success else "failed")
    conn.close()
    print(f"📤 Report inviato: {'OK' if success else 'FALLITO'}")

if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "surebets"
    
    if cmd == "surebets":
        notify_surebets()
    elif cmd == "odds_change":
        notify_odds_change()
    elif cmd == "dashboard":
        send_mini_dashboard()
    elif cmd == "report":
        send_report()
    else:
        print(f"Usage: {sys.argv[0]} [surebets|odds_change|dashboard|report]")
