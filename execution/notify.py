#!/usr/bin/env python3
"""WinBet Notify — Send notifications via Hermes CLI (reuses configured channels).

This script sends notifications through the Hermes gateway using `hermes send`.
It automatically reuses whatever channels are already configured in Hermes
(Telegram, Discord, Slack, etc.) without needing separate API keys.

Usage from other scripts:
    from notify import notify, report_summary, mini_dashboard
    notify("WinBet alert: new sure bet found!")
"""
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent
LOG_PATH = ROOT / ".tmp" / "notifications.log"

def log(msg: str):
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now(timezone.utc).isoformat()}] {msg}\n")
    print(msg)

def hermes_send(message: str, subject: str = "WinBet") -> bool:
    """Send a message via Hermes CLI to the default configured channel(s)."""
    try:
        cmd = ["hermes", "send", "--to", "telegram"]
        if subject:
            cmd += ["--subject", subject]
        cmd += [message]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(ROOT),
        )
        if result.returncode == 0:
            log("[Hermes/Telegram] Sent successfully.")
            return True
        else:
            log(f"[Hermes/Telegram] Failed: {result.stderr[:200]}")
            return False
    except FileNotFoundError:
        log("[Hermes] 'hermes' CLI not found in PATH. Is Hermes installed?")
        return False
    except subprocess.TimeoutExpired:
        log("[Hermes] Send timeout.")
        return False
    except Exception as exc:
        log(f"[Hermes] Error: {exc}")
        return False

def notify(text: str, subject: str = "WinBet Alert") -> dict:
    """Send to all configured Hermes channels."""
    ok = hermes_send(text, subject)
    return {
        "hermes_telegram": ok,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

def report_summary(scrape_results: list[dict], surebets: list[dict]) -> str:
    """Build a text summary for notifications."""
    total_events = sum(r.get("events", 0) for r in scrape_results)
    total_odds = sum(r.get("odds_upserted", 0) for r in scrape_results)
    lines = [
        f"WinBet Report — {datetime.now(timezone.utc).strftime('%H:%M UTC')}",
        f"📊 Eventi raccolti: {total_events}",
        f"📈 Quote aggiornate: {total_odds}",
        f"🎯 Sure bet: {len(surebets)}",
    ]
    if surebets:
        lines.append("\nSure Bet rilevate:")
        for s in surebets[:5]:
            lines.append(f"  • {s['home']} vs {s['away']} — profitto {s['profit']}%")
    return "\n".join(lines)

def mini_dashboard(events: list[dict], market="1X2") -> str:
    """Build a compact dashboard for messaging."""
    lines = [f"WinBet Mini-Dashboard | Mercato: {market}", ""]
    for ev in events[:10]:
        home = ev.get("home_team", "")
        away = ev.get("away_team", "")
        sel_str = ", ".join([f"{s['name']}={s['odds']}({s['bookmaker']})" for s in ev.get("selections", [])])
        lines.append(f"⚽ {home} vs {away}")
        lines.append(f"   {sel_str}")
        lines.append("")
    return "\n".join(lines)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="WinBet Notify")
    parser.add_argument("--text", required=True, help="Message text")
    parser.add_argument("--subject", default="WinBet Alert", help="Subject line")
    args = parser.parse_args()
    notify(args.text, args.subject)
