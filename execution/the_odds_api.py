#!/usr/bin/env python3
"""WinBet TheOddsAPI Client — Fetch odds from the-odds-api.com and store in DB."""
# /// script
# requires-python = ">=3.10"
# dependencies = ["httpx"]
# ///

import argparse
import hashlib
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).parent.parent
DB_CONFIG = ROOT / "config" / "db_config.json"
API_KEY = os.environ.get("THE_ODDS_API_KEY", "")
BASE_URL = "https://api.the-odds-api.com/v4"

SPORT_KEYS = {
    "serie-a": "soccer_italy_serie_a",
    "premier-league": "soccer_epl",
    "la-liga": "soccer_spain_la_liga",
    "bundesliga": "soccer_germany_bundesliga",
    "ligue-1": "soccer_france_ligue_one",
    "champions-league": "soccer_uefa_champs_league",
    "europa-league": "soccer_uefa_europa_league",
    "serie-b": "soccer_italy_serie_b",
    "eredivisie": "soccer_netherlands_eredivisie",
    "liga-portugal": "soccer_portugal_primeira_liga",
}

def get_db():
    cfg = json.loads(DB_CONFIG.read_text(encoding="utf-8"))
    conn = sqlite3.connect(cfg["path"], check_same_thread=False)
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn

def event_hash(home: str, away: str, start: str) -> str:
    return hashlib.sha256(f"{home}|{away}|{start}".encode()).hexdigest()[:16]

def upsert_event(conn, ev: dict) -> int:
    home = ev.get("home_team", "")
    away = ev.get("away_team", "")
    start = ev.get("start_time", "")
    competition = ev.get("competition", "")
    league = ev.get("league", "")
    eid = ev.get("event_id", "") or event_hash(home, away, start)
    cur = conn.execute(
        "SELECT id FROM events WHERE event_id=? AND home_team=? AND away_team=?",
        (eid, home, away),
    )
    row = cur.fetchone()
    now = datetime.now(timezone.utc).isoformat()
    if row:
        conn.execute(
            "UPDATE events SET start_time=?, competition=?, league=?, scraped_at=? WHERE id=?",
            (start, competition, league, now, row[0]),
        )
        return row[0]
    cur = conn.execute(
        "INSERT INTO events(event_id,home_team,away_team,start_time,competition,league,scraped_at) VALUES (?,?,?,?,?,?,?)",
        (eid, home, away, start, competition, league, now),
    )
    return cur.lastrowid

def upsert_odds(conn, event_rowid: int, bookmaker: str, market_type: str, selection: str, odds: float) -> None:
    if odds < 1.01:
        return
    now = datetime.now(timezone.utc).isoformat()
    cur = conn.execute(
        "SELECT id, odds FROM odds WHERE event_id=? AND bookmaker=? AND market_type=? AND selection=?",
        (event_rowid, bookmaker, market_type, selection),
    )
    row = cur.fetchone()
    if row:
        old_odds = row[1]
        if abs(old_odds - odds) >= 0.01:
            change_pct = round(((odds - old_odds) / old_odds) * 100, 2) if old_odds else 0.0
            conn.execute(
                "UPDATE odds SET odds=?, scraped_at=? WHERE id=?",
                (odds, now, row[0]),
            )
            conn.execute(
                "INSERT INTO odds_history(event_id,bookmaker,market_type,selection,odds_old,odds_new,change_pct,changed_at) VALUES (?,?,?,?,?,?,?,?)",
                (event_rowid, bookmaker, market_type, selection, old_odds, odds, change_pct, now),
            )
    else:
        conn.execute(
            "INSERT INTO odds(event_id,bookmaker,market_type,selection,odds,scraped_at) VALUES (?,?,?,?,?,?)",
            (event_rowid, bookmaker, market_type, selection, odds, now),
        )

def fetch_odds(sport_key: str, markets: str = "h2h", region: str = "eu") -> list[dict]:
    if not API_KEY:
        print("ERROR: THE_ODDS_API_KEY not set in environment.")
        return []
    url = f"{BASE_URL}/sports/{sport_key}/odds"
    params = {
        "apiKey": API_KEY,
        "regions": region,
        "markets": markets,
        "oddsFormat": "decimal",
    }
    try:
        r = httpx.get(url, params=params, timeout=30)
        r.raise_for_status()
        return r.json()
    except httpx.HTTPStatusError as exc:
        print(f"HTTP error {exc.response.status_code}: {exc.response.text[:200]}")
        return []
    except Exception as exc:
        print(f"Request error: {exc}")
        return []

def ingest_competition(comp_key: str, comp_name: str, markets: str = "h2h") -> dict:
    sport_key = SPORT_KEYS.get(comp_key)
    if not sport_key:
        return {"status": "skipped", "competition": comp_key, "reason": "no sport_key mapping"}
    raw = fetch_odds(sport_key, markets)
    if not raw:
        return {"status": "empty", "competition": comp_key, "events": 0}
    conn = get_db()
    total_odds = 0
    for event in raw:
        ev = {
            "event_id": event.get("id", ""),
            "home_team": event.get("home_team", ""),
            "away_team": event.get("away_team", ""),
            "start_time": event.get("commence_time", ""),
            "competition": comp_key,
            "league": comp_name,
        }
        event_rowid = upsert_event(conn, ev)
        for bk_data in event.get("bookmakers", []):
            bk_name = bk_data.get("title", "unknown")
            for mkt in bk_data.get("markets", []):
                mkey = mkt.get("key", "h2h")
                mtype = "1X2" if mkey == "h2h" else mkey.upper()
                for outcome in mkt.get("outcomes", []):
                    sel = outcome.get("name", "")
                    odds = float(outcome.get("price", 0))
                    upsert_odds(conn, event_rowid, bk_name, mtype, sel, odds)
                    total_odds += 1
    conn.commit()
    conn.close()
    return {
        "status": "ok",
        "competition": comp_key,
        "events": len(raw),
        "odds_upserted": total_odds,
        "scraped_at": datetime.now(timezone.utc).isoformat(),
    }

def ingest_all(markets: str = "h2h") -> list[dict]:
    results = []
    for comp_key, sport_key in SPORT_KEYS.items():
        print(f"Fetching {comp_key} ({sport_key}) ...")
        res = ingest_competition(comp_key, comp_key, markets)
        results.append(res)
        print(f"  → {res}")
    return results

def main():
    parser = argparse.ArgumentParser(description="WinBet TheOddsAPI client")
    parser.add_argument("--competition", default=None, help="Competition key")
    parser.add_argument("--markets", default="h2h", help="Markets (h2h,totals,spreads)")
    parser.add_argument("--all", action="store_true", help="Ingest all mapped competitions")
    args = parser.parse_args()
    if args.all:
        results = ingest_all(args.markets)
        ok = [r for r in results if r["status"] == "ok"]
        print(f"\nDone. {len(ok)}/{len(results)} competitions ingested.")
    elif args.competition:
        res = ingest_competition(args.competition, args.competition, args.markets)
        print(json.dumps(res, indent=2, ensure_ascii=False))
    else:
        print("Use --competition KEY or --all")

if __name__ == "__main__":
    main()
