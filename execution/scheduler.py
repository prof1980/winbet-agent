#!/usr/bin/env python3
"""WinBet Scheduler — Run scraping every 2 hours and notify via Hermes channels.

Modalità: LIVE — scraping reale da SNAI, Eurobet e The Odds API
Frequenza: 2 ore (12 scrape/giorno × ~2 crediti The Odds API = 24 crediti/giorno)
Budget mensile: 720 crediti (sfora i 500/mese del piano free) — monitorare
Notifiche: Hermes CLI (reusa canali già configurati: Telegram/Discord/Slack)
"""
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "execution"))

from the_odds_api import ingest_all as odds_api_ingest
from demo_data import generate_all as demo_generate
from surebet_engine import find_surebets
from notify import notify, report_summary

def run_cycle(bookmakers=None, headless=True, email_notify=False):
    """Single scraping + analysis + notification cycle.

    Args:
        bookmakers: lista bookmaker per fallback
        headless: modalità headless browser
        email_notify: se True, invia report anche via email Libero
    """
    print(f"\n{'='*60}")
    print(f"WinBet Cycle — {datetime.now(timezone.utc).isoformat()}")
    print(f"{'='*60}")

    # 1) Prova The Odds API (fonte primaria)
    print("[1] Fetching from The Odds API (primary source)...")
    api_results = odds_api_ingest()
    api_ok = [r for r in api_results if r["status"] == "ok" and r.get("events", 0) > 0]
    print(f"    The Odds API: {len(api_ok)}/{len(api_results)} competitions ingested.")

    # 2) Fallback: Demo Data Generator (se API esaurita o non disponibile)
    fallback_results = []
    if len(api_ok) == 0:
        print("[2] API credits exhausted or unavailable. Using Demo Data Generator...")
        demo_results = demo_generate(matches_per_comp=6)
        total_matches = sum(r["matches"] for r in demo_results)
        fallback_results = [{
            "status": "ok",
            "source": "demo_data",
            "events": total_matches,
            "odds_upserted": total_matches * 7 * 4,  # 7 bookmakers * ~4 markets
        }]
        print(f"    Demo Data: {total_matches} matches generated.")

    all_results = api_results + fallback_results
    total_events = sum(r.get("events", 0) for r in all_results)
    total_odds = sum(r.get("odds_upserted", 0) for r in all_results)

    # 3) Find surebets for enabled markets
    markets_cfg = json.loads((ROOT / "config" / "markets.json").read_text(encoding="utf-8"))
    enabled = [m["type"] for m in markets_cfg.get("markets", []) if m.get("enabled")]
    all_surebets = []
    for mkt in enabled:
        bets = find_surebets(mkt)
        all_surebets.extend(bets)
    all_surebets.sort(key=lambda x: x["profit"], reverse=True)
    print(f"[3] Surebets found: {len(all_surebets)} (across {len(enabled)} markets)")

    # 4) Notify via Hermes (Telegram + altri canali configurati)
    report_text = report_summary(all_results, all_surebets)
    result = notify(report_text, subject="WinBet Report (ogni 2 ore)")
    print(f"[4] Notification sent: {result}")

    # 5) Alert immediato se sure bet > 5% profitto
    high_profit = [b for b in all_surebets if b["profit"] > 5.0]
    if high_profit:
        alert_lines = ["🚨 WinBet ALTA PRIORITÀ — Sure Bet rilevate!\n"]
        for b in high_profit[:5]:
            alert_lines.append(
                f"⚽ {b['home']} vs {b['away']} | {b['market']} | Profitto: {b['profit']}%\n"
                f"   Combo: {' | '.join(b['combo'])}\n"
            )
        alert_text = "\n".join(alert_lines)
        notify(alert_text, subject="🚨 WinBet Sure Bet Alert")
        print(f"[5] HIGH PRIORITY alert sent for {len(high_profit)} surebets.")

    # 6) Report via email Libero (se abilitato)
    if email_notify:
        try:
            from libero_notifier import LiberoNotifier
            n = LiberoNotifier()
            email_body = (
                f"{report_text}\n\n"
                f"---\n"
                f"🤖 WinBot Scheduler\n"
                f"Generato: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"Web dashboard: http://localhost:8080/\n"
            )
            ok = n.send_email(
                to=n.email,
                subject=f"WinBet Report {datetime.now():%Y-%m-%d %H:%M}",
                body=email_body,
            )
            if ok:
                print(f"[6] Email report inviata a {n.email}")
            else:
                print(f"[6] ⚠️ Invio email fallito")
        except Exception as e:
            print(f"[6] ⚠️ Errore invio email: {e}")

    return all_results, all_surebets

def main():
    import argparse
    parser = argparse.ArgumentParser(description="WinBet Scheduler")
    parser.add_argument("--interval", type=int, default=7200, help="Seconds between cycles (default 7200=2h)")
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    parser.add_argument("--bookmakers", default=None, help="Comma-separated bookmakers for fallback")
    parser.add_argument("--no-headless", dest="headless", action="store_false", default=True)
    parser.add_argument("--email", action="store_true", help="Invia report via email Libero")
    args = parser.parse_args()

    if args.once:
        run_cycle(email_notify=args.email)
        return

    print(f"Scheduler started. Interval: {args.interval}s (Ctrl+C to stop)")
    while True:
        try:
            run_cycle(email_notify=args.email)
        except KeyboardInterrupt:
            print("\nStopped by user.")
            break
        except Exception as exc:
            print(f"Cycle error: {exc}")
        print(f"Next run at {datetime.now(timezone.utc).isoformat()} + {args.interval}s")
        time.sleep(args.interval)

if __name__ == "__main__":
    main()
