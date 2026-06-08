#!/usr/bin/env python3
"""WinBet SureBet Engine — detect arbitrage opportunities across bookmakers."""
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///

import argparse
import json
import sqlite3
from pathlib import Path
from itertools import product

ROOT = Path(__file__).parent.parent
DB_CONFIG = ROOT / "config" / "db_config.json"

def get_db():
    cfg = json.loads(DB_CONFIG.read_text(encoding="utf-8"))
    conn = sqlite3.connect(cfg["path"], check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def find_surebets(market_type="1X2", threshold=0.0):
    """Find arbitrage opportunities.

    Args:
        market_type: Market to analyze (1X2, DC, OU25, etc.)
        threshold: Minimum profit percentage to report (0 = all positive)

    Returns:
        List of surebet dicts sorted by profit descending.
    """
    conn = get_db()
    cur = conn.execute("""
        SELECT e.id, e.home_team, e.away_team, e.start_time, e.competition,
               o.bookmaker, o.market_type, o.selection, o.odds
        FROM events e
        LEFT JOIN odds o ON o.event_id = e.id
        WHERE o.market_type = ?
        ORDER BY e.id, o.selection, o.odds DESC
    """, (market_type,))
    rows = cur.fetchall()
    conn.close()

    events = {}
    for r in rows:
        key = r["id"]
        if key not in events:
            events[key] = {
                "home": r["home_team"], "away": r["away_team"],
                "start": r["start_time"], "comp": r["competition"],
                "selections": {},
            }
        sel = r["selection"]
        if sel not in events[key]["selections"]:
            events[key]["selections"][sel] = []
        events[key]["selections"][sel].append({"bk": r["bookmaker"], "odds": r["odds"]})

    surebets = []
    for evid, ev in events.items():
        sels = ev["selections"]
        if not sels:
            continue
        # For markets with multiple mutually exclusive outcomes
        sel_names = list(sels.keys())
        if len(sel_names) < 2:
            continue
        # Generate all bookmaker combinations across selections
        combos = list(product(*[sels[n] for n in sel_names]))
        for combo in combos:
            implied = sum(1 / c["odds"] for c in combo)
            if implied < 1.0 - threshold:
                profit = (1.0 - implied) * 100
                # Build detail lines
                details = []
                for i, sel_name in enumerate(sel_names):
                    details.append(f"{sel_name}@{combo[i]['bk']}={combo[i]['odds']}")
                surebets.append({
                    "event_id": evid,
                    "home": ev["home"], "away": ev["away"],
                    "competition": ev["comp"],
                    "start": ev["start"],
                    "market": market_type,
                    "selections": sel_names,
                    "combo": details,
                    "implied": round(implied, 4),
                    "profit": round(profit, 2),
                })
    return sorted(surebets, key=lambda x: x["profit"], reverse=True)

def main():
    parser = argparse.ArgumentParser(description="WinBet SureBet Engine")
    parser.add_argument("--market", default="1X2", help="Market type")
    parser.add_argument("--threshold", type=float, default=0.0, help="Minimum profit %")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    bets = find_surebets(args.market, args.threshold)
    if args.json:
        print(json.dumps(bets, indent=2, ensure_ascii=False))
    else:
        if not bets:
            print(f"No surebets found for market {args.market} (threshold {args.threshold}%)")
            return
        print(f"Found {len(bets)} surebets for {args.market}:\n")
        for b in bets:
            print(f"  {b['home']} vs {b['away']} | {b['market']} | profit {b['profit']}%")
            for c in b["combo"]:
                print(f"    → {c}")

if __name__ == "__main__":
    main()
