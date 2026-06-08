#!/usr/bin/env python3
"""Scrape odds via bookmaker_scraper.py and upsert into SQLite database."""
# /// script
# requires-python = ">=3.10"
# dependencies = ["httpx"]
# ///

import argparse
import hashlib
import json
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# --- Config paths ---
ROOT = Path(__file__).parent.parent
CONFIG_DIR = ROOT / "config"
DB_CONFIG = ROOT / "config" / "db_config.json"
MARKETS_FILE = ROOT / "config" / "markets.json"
COMPETITIONS_FILE = ROOT / "config" / "competitions.json"
SCRAPER_SCRIPT = ROOT / "scripts" / "bookmaker_scraper.py"

# --- DB helpers ---

def get_db_conn():
    cfg = json.loads(DB_CONFIG.read_text(encoding="utf-8"))
    conn = sqlite3.connect(cfg["path"], check_same_thread=False)
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def event_hash(home: str, away: str, start: str) -> str:
    return hashlib.sha256(f"{home}|{away}|{start}".encode()).hexdigest()[:16]


def upsert_event(conn: sqlite3.Connection, ev: dict) -> int:
    """Insert or update event and return its row id."""
    home = ev.get("home_team", "")
    away = ev.get("away_team", "")
    start = ev.get("start_time", "")
    competition = ev.get("competition", "")
    league = ev.get("league", "")
    eid = ev.get("id", "") or event_hash(home, away, start)
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


def upsert_odds(conn: sqlite3.Connection, event_rowid: int, bookmaker: str, market: dict, selection: dict) -> None:
    """Insert or update a single selection odd and log history if changed."""
    mtype = market.get("market_type", market.get("type", "UNKNOWN"))
    sel_name = selection.get("name", "")
    sel_label = selection.get("label", sel_name)
    odds_val = float(selection.get("odds", 0))
    if odds_val < 1.01:
        return
    now = datetime.now(timezone.utc).isoformat()
    cur = conn.execute(
        "SELECT id, odds FROM odds WHERE event_id=? AND bookmaker=? AND market_type=? AND selection=?",
        (event_rowid, bookmaker, mtype, sel_name),
    )
    row = cur.fetchone()
    if row:
        old_odds = row[1]
        if abs(old_odds - odds_val) >= 0.01:
            change_pct = round(((odds_val - old_odds) / old_odds) * 100, 2) if old_odds else 0.0
            conn.execute(
                "UPDATE odds SET odds=?, scraped_at=? WHERE id=?",
                (odds_val, now, row[0]),
            )
            conn.execute(
                "INSERT INTO odds_history(event_id,bookmaker,market_type,selection,odds_old,odds_new,change_pct,changed_at) VALUES (?,?,?,?,?,?,?,?)",
                (event_rowid, bookmaker, mtype, sel_name, old_odds, odds_val, change_pct, now),
            )
    else:
        conn.execute(
            "INSERT INTO odds(event_id,bookmaker,market_type,selection,odds,scraped_at) VALUES (?,?,?,?,?,?)",
            (event_rowid, bookmaker, mtype, sel_name, odds_val, now),
        )


def load_json(p: Path) -> Any:
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def get_enabled_markets():
    data = load_json(MARKETS_FILE)
    return {m["type"] for m in data.get("markets", []) if m.get("enabled", True)}


def get_enabled_competitions():
    data = load_json(COMPETITIONS_FILE)
    return [c for c in data.get("competitions", []) if c.get("priority") in ("high", "medium")]


def run_scraper(bookmaker: str, sport: str, competition: str, output_path: Path, headless: bool = True) -> dict:
    """Invoke scripts/bookmaker_scraper.py via uv run or python directly."""
    cmd = [
        sys.executable, str(SCRAPER_SCRIPT),
        "scrape",
        "--bookmaker", bookmaker,
        "--sport", sport,
        "--competition", competition,
        "--output", str(output_path),
    ]
    if not headless:
        cmd.append("--no-headless")
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=120)
    except subprocess.CalledProcessError as exc:
        print(f"  ✗ Scraper failed for {bookmaker}/{competition}: {exc.stderr}")
        return {}
    except FileNotFoundError:
        print(f"  ✗ Scraper script not found: {SCRAPER_SCRIPT}")
        return {}
    try:
        return json.loads(output_path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"  ✗ Failed to parse scraper output: {exc}")
        return {}


# --- Main ingestion ---

def ingest(bookmaker: str, sport: str, competition: str, headless: bool = True) -> dict:
    out = ROOT / ".tmp" / f"{bookmaker}_{competition}.json"
    raw = run_scraper(bookmaker, sport, competition, out, headless)
    if not raw:
        return {"status": "error", "bookmaker": bookmaker, "competition": competition, "events": 0}

    enabled_markets = get_enabled_markets()
    conn = get_db_conn()
    total = 0
    events = raw.get("events", [])
    for ev in events:
        event_rowid = upsert_event(conn, ev)
        for mkt in ev.get("markets", []):
            mtype = mkt.get("market_type", mkt.get("type", ""))
            if mtype not in enabled_markets:
                continue
            for sel in mkt.get("selections", []):
                upsert_odds(conn, event_rowid, bookmaker, mkt, sel)
                total += 1
    conn.commit()
    conn.close()
    return {
        "status": "ok",
        "bookmaker": bookmaker,
        "competition": competition,
        "events": len(events),
        "odds_upserted": total,
        "scraped_at": datetime.now(timezone.utc).isoformat(),
    }


def scrape_all(bookmakers: list[str] = None, headless: bool = True) -> list[dict]:
    if bookmakers is None:
        bookmakers = ["snai", "eurobet", "goldbet", "williamhill", "sisal", "lottomatica", "oddsportal"]
    comps = get_enabled_competitions()
    results = []
    for bk in bookmakers:
        for comp in comps:
            print(f"Scraping {bk} → {comp['key']} ...")
            res = ingest(bk, "calcio", comp["key"], headless)
            results.append(res)
    return results


# --- CLI ---

def main():
    parser = argparse.ArgumentParser(description="WinBet: scrape odds and store in DB")
    parser.add_argument("--bookmaker", default="snai", help="Bookmaker key")
    parser.add_argument("--competition", default="serie-a", help="Competition key")
    parser.add_argument("--sport", default="calcio", help="Sport")
    parser.add_argument("--all", action="store_true", help="Scrape all enabled bookmakers and competitions")
    parser.add_argument("--no-headless", dest="headless", action="store_false", default=True, help="Show browser")
    args = parser.parse_args()

    if args.all:
        results = scrape_all(headless=args.headless)
        ok = sum(1 for r in results if r["status"] == "ok" and r["events"] > 0)
        print(f"\nDone. {ok}/{len(results)} scrapes returned events.")
        for r in results:
            print(f"  {r['bookmaker']:15s} {r['competition']:20s} → events={r.get('events',0)} odds={r.get('odds_upserted',0)}")
    else:
        res = ingest(args.bookmaker, args.sport, args.competition, args.headless)
        print(json.dumps(res, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
