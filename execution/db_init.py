#!/usr/bin/env python3
"""Initialize WinBet SQLite database with tables for events, odds and history."""
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///

import json
import sqlite3
import sys
from pathlib import Path

def main():
    config_path = Path(__file__).parent.parent / "config" / "db_config.json"
    if not config_path.exists():
        print("Config not found:", config_path)
        sys.exit(1)
    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    db_path = cfg["path"]
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    if cfg.get("wal_mode", True):
        conn.execute("PRAGMA journal_mode=WAL;")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT,
            home_team TEXT NOT NULL,
            away_team TEXT NOT NULL,
            start_time TEXT,
            competition TEXT,
            league TEXT,
            scraped_at TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_events_teams ON events(home_team, away_team);
        CREATE INDEX IF NOT EXISTS idx_events_comp ON events(competition);
        CREATE TABLE IF NOT EXISTS odds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id INTEGER NOT NULL,
            bookmaker TEXT NOT NULL,
            market_type TEXT NOT NULL,
            selection TEXT NOT NULL,
            odds REAL NOT NULL,
            scraped_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_odds_event ON odds(event_id);
        CREATE INDEX IF NOT EXISTS idx_odds_bookmaker ON odds(bookmaker);
        CREATE INDEX IF NOT EXISTS idx_odds_market ON odds(market_type, selection);
        CREATE TABLE IF NOT EXISTS odds_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id INTEGER NOT NULL,
            bookmaker TEXT NOT NULL,
            market_type TEXT NOT NULL,
            selection TEXT NOT NULL,
            odds_old REAL,
            odds_new REAL,
            change_pct REAL,
            changed_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_hist_event ON odds_history(event_id);
    """)
    conn.commit()
    conn.close()
    print(f"Database initialized: {db_path}")

if __name__ == "__main__":
    main()
