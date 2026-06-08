#!/usr/bin/env python3
"""The Odds API Scraper - Integrazione WinBet cross-bookmaker.

Sport target:
  - soccer_fifa_world_cup    → Mondiali 2026
  - soccer_international_friendlies → Amichevoli (se disponibile)

Mercati:
  - h2h     → 1X2
  - totals  → Over/Under
  - btts    → Gol/NoGol (dove supportato)

Region: eu (quote europee)

La chiave API viene letta da $ODDS_API_KEY o passata via --api-key.
"""
# /// script
# requires-python = ">=3.10"
# dependencies = ["curl_cffi"]
# ///

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# Carica credenziali da .env nella root progetto
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env")

from curl_cffi import requests as curl_requests

DEFAULT_DB = Path(__file__).parent.parent / "winbet.db"

THE_ODDS_API_BASE = "https://api.the-odds-api.com/v4"

SPORTS_MAP = {
    "mondiali": {
        "key": "soccer_fifa_world_cup",
        "regions": ["eu"],
        "markets": ["h2h", "totals"],  # btts non supportato per Mondiali
    },
}

HEADERS = {
    "Accept": "application/json",
    "Accept-Language": "it-IT,it;q=0.9",
}


class TheOddsApiScraper:
    def __init__(self, api_key: str | None = None, db_path: str | None = None):
        self.api_key = (
            api_key
            or os.environ.get("ODDS_API_KEY", "")
            or os.environ.get("THE_ODDS_API_KEY", "")
        )
        if not self.api_key:
            raise RuntimeError("API key mancante. Passa --api-key o setta ODDS_API_KEY")
        self.db_path = str(db_path or DEFAULT_DB)
        self.events_scraped = 0
        self.odds_saved = 0
        self.credits_used = 0

    # ------------------------------------------------------------------
    # API calls
    # ------------------------------------------------------------------
    def _get(self, path: str, params: dict | None = None) -> dict | None:
        url = f"{THE_ODDS_API_BASE}{path}"
        try:
            resp = curl_requests.get(
                url,
                headers=HEADERS,
                params=params,
                impersonate="chrome136",
                timeout=20,
            )
            if resp.status_code != 200:
                print(f"  ⚠ The Odds API HTTP {resp.status_code}: {resp.text[:200]}")
                return None
            return resp.json()
        except Exception as exc:
            print(f"  ✗ The Odds API fetch failed: {exc}")
            return None

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------
    def _parse_event(self, raw: dict, sport_key: str) -> dict | None:
        """Parsa un evento da The Odds API in formato WinBet."""
        home = raw.get("home_team", "")
        away = raw.get("away_team", "")
        if not home or not away:
            return None

        event_id = raw.get("id", "")
        start_time = raw.get("commence_time", "")
        competition = raw.get("sport_title", sport_key)

        # Mercati
        markets = []
        for bookmaker in raw.get("bookmakers", [])[:5]:  # Top 5 bookmakers per evento
            bk_name = bookmaker.get("key", "unknown")
            for mkt in bookmaker.get("markets", []):
                mkt_key = mkt.get("key", "")
                selections = []
                for outcome in mkt.get("outcomes", []):
                    selections.append({
                        "name": outcome.get("name", ""),
                        "label": outcome.get("name", ""),
                        "odds": round(float(outcome.get("price", 0)), 2),
                        "point": outcome.get("point"),
                        "bookmaker": bk_name,
                    })

                if selections:
                    markets.append({
                        "market_type": mkt_key,
                        "market_name": f"{mkt_key} ({bk_name})",
                        "bookmaker": bk_name,
                        "selections": selections,
                    })

        if not markets:
            return None

        return {
            "event_id": f"toa_{event_id}",
            "home_team": home,
            "away_team": away,
            "event_description": f"{home} - {away}",
            "start_time": start_time,
            "competition": competition,
            "live": False,
            "markets": markets,
        }

    # ------------------------------------------------------------------
    # Scraping
    # ------------------------------------------------------------------
    def scrape_sport(self, sport_config: dict) -> list[dict]:
        """Scrape un singolo sport da The Odds API."""
        sport_key = sport_config["key"]
        regions = ",".join(sport_config.get("regions", ["eu"]))
        markets = ",".join(sport_config.get("markets", ["h2h"]))
        # timezone europeo
        tz = "Europe/Rome"

        print(f"  🔍 The Odds API: {sport_key} | regions={regions} | markets={markets}")

        params = {
            "apiKey": self.api_key,
            "regions": regions,
            "markets": markets,
            "oddsFormat": "decimal",
            "dateFormat": "iso",
            "tz": tz,
        }

        data = self._get(f"/sports/{sport_key}/odds", params)
        if not data:
            return []

        if isinstance(data, dict) and "error" in data:
            print(f"  ⚠ API error: {data.get('error', 'unknown')}")
            return []

        # The Odds API returns a list of events directly
        events = []
        for raw in data:
            ev = self._parse_event(raw, sport_key)
            if ev:
                events.append(ev)

        # Stima crediti usati: 1 per sport*regione per mercato
        n_regions = len(sport_config.get("regions", ["eu"]))
        n_markets = len(sport_config.get("markets", ["h2h"]))
        self.credits_used += n_regions * n_markets

        print(f"  ✓ Parsed {len(events)} events (credits used this run: ~{self.credits_used})")
        return events

    def scrape_all(self, sport_keys: list[str] | None = None) -> list[dict]:
        """Scrape tutti gli sport configurati."""
        if sport_keys is None:
            sport_keys = ["mondiali"]

        all_events = []
        for key in sport_keys:
            config = SPORTS_MAP.get(key)
            if not config:
                print(f"  ⚠ Sport config '{key}' non trovato")
                continue
            events = self.scrape_sport(config)
            all_events.extend(events)
        return all_events

    # ------------------------------------------------------------------
    # Database persistence
    # ------------------------------------------------------------------
    def save_to_db(self, events: list[dict]) -> None:
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        now = datetime.now(timezone.utc).isoformat()

        for ev in events:
            match_id = ev["event_id"]
            
            # Parse date/time
            match_date, match_time = "", ""
            start = ev.get("start_time", "")
            if start and "T" in start:
                parts = start.split("T")
                match_date = parts[0]
                match_time = parts[1][:5] if len(parts[1]) >= 5 else parts[1]

            cur.execute("""
                INSERT INTO matches (match_id, league_id, home_team, away_team, match_date, match_time, status, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(match_id) DO UPDATE SET
                    league_id=excluded.league_id,
                    home_team=excluded.home_team,
                    away_team=excluded.away_team,
                    match_date=excluded.match_date,
                    match_time=excluded.match_time,
                    updated_at=excluded.updated_at
            """, (match_id, ev["competition"], ev["home_team"], ev["away_team"],
                  match_date, match_time, "scheduled", now))
            self.events_scraped += 1

            for mkt in ev.get("markets", []):
                bk = mkt.get("bookmaker", "unknown")
                for sel in mkt.get("selections", []):
                    cur.execute("""
                        INSERT INTO odds_history (match_id, bookmaker_id, market_type, selection_name, odds_value, recorded_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (match_id, bk, mkt["market_type"], sel["name"], sel["odds"], now))

                    cur.execute("""
                        INSERT INTO odds (match_id, bookmaker_id, market_type, selection_name, selection_label, odds_value, odds_decimal, scraped_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT DO UPDATE SET
                            odds_value=excluded.odds_value,
                            odds_decimal=excluded.odds_decimal,
                            scraped_at=excluded.scraped_at,
                            updated_at=excluded.updated_at
                    """, (match_id, bk, mkt["market_type"], sel["name"], sel.get("label", ""), sel["odds"], sel["odds"], now, now))
                    self.odds_saved += 1

        conn.commit()

        # Log scrape
        cur.execute("""
            INSERT INTO scrape_log (bookmaker_id, league_id, matches_found, odds_found, errors, started_at, completed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, ("the_odds_api", "mondiali", self.events_scraped, self.odds_saved,
              "", now, now))
        conn.commit()
        conn.close()

        print(f"  💾 Saved {self.events_scraped} events, {self.odds_saved} odds")
        print(f"  📊 Credits used this run: ~{self.credits_used}")


def main() -> None:
    parser = argparse.ArgumentParser(description="The Odds API Scraper for WinBet")
    parser.add_argument(
        "--api-key",
        default=os.environ.get("ODDS_API_KEY", "") or os.environ.get("THE_ODDS_API_KEY", ""),
        help="The Odds API key"
    )
    parser.add_argument("--sports", default="mondiali", help="Comma-separated sport keys")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="SQLite database path")
    parser.add_argument("--output", default="", help="Optional JSON output path")
    parser.add_argument("--store-db", action="store_true", help="Persist to database")
    args = parser.parse_args()

    if not args.api_key:
        print("❌ ERRORE: API key mancante. Passa --api-key o setta ODDS_API_KEY")
        sys.exit(1)

    sport_keys = [k.strip() for k in args.sports.split(",")]

    scraper = TheOddsApiScraper(api_key=args.api_key, db_path=args.db)
    events = scraper.scrape_all(sport_keys)

    result = {
        "scrape_timestamp": datetime.now().isoformat(),
        "source": "the_odds_api",
        "sports": sport_keys,
        "total_events": len(events),
        "credits_used": scraper.credits_used,
        "events": events,
    }

    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        print(f"  ✓ JSON written to {args.output}")

    if args.store_db:
        scraper.save_to_db(events)

    print(f"\n📊 THE ODDS API: {len(events)} events | Credits: ~{scraper.credits_used}/500 used this run")


if __name__ == "__main__":
    main()
